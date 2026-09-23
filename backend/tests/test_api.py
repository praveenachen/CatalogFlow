import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.main import app, get_storage
from app.models import CatalogRecord
from app.storage import LocalCatalogStorage


def make_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    storage_directory = tempfile.TemporaryDirectory()
    app.dependency_overrides[get_storage] = lambda: LocalCatalogStorage(storage_directory.name)
    client = TestClient(app)
    client.storage_directory = storage_directory
    return client, engine


def test_batch_review_preserves_automation_confidence_and_exports():
    client, engine = make_client()
    payload = "sku,item_name,product_type,cost,currency,stock,labels\nA1,trail shoe,womens shoes,not-a-price,usd,18,#sale\n"
    response = client.post("/batches", files={"file": ("catalog.csv", payload, "text/csv")})
    assert response.status_code == 200
    batch = response.json()
    assert batch["batch_id"] == batch["upload_id"]
    assert batch["schema_report"]["profiles"]
    assert batch["attention_count"] == 1
    assert batch["needs_review_count"] == 0
    assert batch["invalid_count"] == 1

    records = client.get(f"/batches/{batch['batch_id']}/records").json()
    record = records[0]
    review_item = client.get(f"/batches/{batch['batch_id']}/review-items").json()[0]
    automated = record["automation_confidence"]
    decision = client.post(
        f"/review-items/{review_item['id']}/decision",
        json={"decision": "edited", "corrected_values": {"cleaned_price": 12.5}},
    )
    assert decision.status_code == 200
    reviewed = decision.json()
    assert reviewed["automation_confidence"] == automated
    assert reviewed["review_status"] == "edited"
    assert reviewed["status"] == "Invalid"
    assert reviewed["exportable"] is True
    refreshed_batch = client.get(f"/batches/{batch['batch_id']}").json()
    assert refreshed_batch["attention_count"] == 0
    assert refreshed_batch["invalid_count"] == 1
    exported = client.get(f"/export/cleaned-catalog?batch_id={batch['batch_id']}")
    assert exported.status_code == 200
    assert exported.text.splitlines()[0] == "sku,product_name,description,category,price,currency,inventory,tags"
    assert exported.headers["content-type"].startswith("text/csv")
    assert 'filename="cleaned-catalog.csv"' in exported.headers["content-disposition"]
    clean_records = client.get(f"/catalog?batch_id={batch['batch_id']}").json()
    assert [item["id"] for item in clean_records] == [record["id"]]

    with Session(engine) as session:
        stored = session.get(CatalogRecord, record["id"])
        assert stored.automation_confidence == automated
        assert json.loads(stored.corrected_values)["cleaned_price"] == 12.5
    app.dependency_overrides.clear()


def test_batch_default_currency_is_persisted_with_provenance():
    client, _ = make_client()
    payload = "product_name,price\nBoot,10\n"
    batch = client.post(
        "/batches?default_currency=USD",
        files={"file": ("catalog.csv", payload, "text/csv")},
    ).json()
    record = client.get(f"/batches/{batch['batch_id']}/records").json()[0]
    trace = next(item for item in record["normalization_trace"] if item["field"] == "currency")
    assert batch["default_currency"] == "USD"
    assert record["cleaned_currency"] == "USD"
    assert trace["rule"] == "configured_default_currency"
    assert trace["original_value"] is None
    app.dependency_overrides.clear()


def test_sample_batch_has_mixed_quality_and_export_policy():
    client, _ = make_client()
    sample = Path(__file__).parents[2] / "frontend" / "public" / "sample-messy-catalog.csv"
    response = client.post("/batches", files={"file": (sample.name, sample.read_bytes(), "text/csv")})
    assert response.status_code == 200
    batch = response.json()
    assert batch["total_records"] == 20
    assert batch["auto_approved_count"] == 16
    assert batch["needs_review_count"] == 1
    assert batch["duplicate_count"] == 1
    assert batch["invalid_count"] == 2
    assert batch["attention_count"] == 4
    assert batch["excluded_count"] == 4
    assert batch["schema_drift_detected"] is True
    assert batch["total_records"] == (
        batch["auto_approved_count"]
        + batch["needs_review_count"]
        + batch["duplicate_count"]
        + batch["invalid_count"]
    )
    assert batch["attention_count"] == batch["needs_review_count"] + batch["duplicate_count"] + batch["invalid_count"]

    processed = client.get(f"/processed-records?batch_id={batch['batch_id']}").json()
    clean = client.get(f"/catalog?batch_id={batch['batch_id']}").json()
    review_queue = client.get(f"/review-queue?batch_id={batch['batch_id']}").json()
    assert len(processed) == batch["total_records"]
    assert len(clean) == batch["auto_approved_count"]
    assert len(review_queue) == batch["attention_count"]
    assert all(record["exportable"] for record in clean)
    assert all(not record["exportable"] for record in review_queue)

    exported = client.get(f"/export/cleaned-catalog?batch_id={batch['batch_id']}")
    lines = exported.text.strip().splitlines()
    assert lines[0] == "sku,product_name,description,category,price,currency,inventory,tags"
    assert len(lines) == batch["auto_approved_count"] + 1
    assert "SKU001,Vintage Vase" not in exported.text
    assert "SKU008,Fitness Band" not in exported.text
    assert "SKU012,Bluetooth Speakers" not in exported.text
    app.dependency_overrides.clear()


def test_reject_keeps_record_out_of_publishable_export():
    client, _ = make_client()
    payload = "product_name,price,currency\n,10,USD\n"
    batch = client.post("/upload-catalog", files={"file": ("catalog.csv", payload, "text/csv")}).json()
    record = client.get("/review-queue").json()[0]
    review_item = client.get(f"/batches/{batch['batch_id']}/review-items").json()[0]
    response = client.post(f"/review-items/{review_item['id']}/decision", json={"decision": "rejected"})
    assert response.json()["exportable"] is False
    refreshed_batch = client.get(f"/batches/{batch['batch_id']}").json()
    assert refreshed_batch["attention_count"] == 0
    assert refreshed_batch["publishable_count"] == 0
    assert refreshed_batch["excluded_count"] == 1
    exported = client.get(f"/export/cleaned-catalog?batch_id={batch['batch_id']}")
    assert exported.status_code == 404
    assert exported.json()["detail"] == "This batch has no publishable records to export."
    app.dependency_overrides.clear()


def test_duplicate_candidate_is_excluded_until_human_approval():
    client, _ = make_client()
    payload = (
        "sku,product_name,price,currency\n"
        "DUP-1,First Product,10,USD\n"
        "DUP-1,Second Product,12,USD\n"
    )
    batch = client.post("/batches", files={"file": ("duplicates.csv", payload, "text/csv")}).json()
    processed = client.get(f"/batches/{batch['batch_id']}/records").json()
    duplicate = next(record for record in processed if record["status"] == "Duplicate")
    assert duplicate["exportable"] is False
    assert all(
        record["id"] != duplicate["id"]
        for record in client.get(f"/catalog?batch_id={batch['batch_id']}").json()
    )

    review_items = client.get(f"/batches/{batch['batch_id']}/review-items").json()
    review_item = next(item for item in review_items if item["record_id"] == duplicate["id"])
    confidence = duplicate["automation_confidence"]
    approved = client.post(f"/review-items/{review_item['id']}/decision", json={"decision": "approved"}).json()
    assert approved["status"] == "Duplicate"
    assert approved["review_status"] == "approved"
    assert approved["automation_confidence"] == confidence
    assert approved["exportable"] is True
    assert duplicate["cleaned_product_name"] in client.get(
        f"/export/cleaned-catalog?batch_id={batch['batch_id']}"
    ).text
    app.dependency_overrides.clear()


def test_dashboard_and_default_exports_are_latest_batch_scoped():
    client, _ = make_client()
    first = "product_name,price,currency,inventory\nOld Product,10,USD,2\n"
    first_batch = client.post("/batches", files={"file": ("first.csv", first, "text/csv")}).json()
    second = (
        "product_name,price,currency,inventory\n"
        "New Good,20,USD,3\n"
        "New Bad,21,USD,bad\n"
    )
    second_batch = client.post("/batches", files={"file": ("second.csv", second, "text/csv")}).json()

    latest = client.get("/latest-batch").json()
    clean = client.get("/catalog").json()
    review = client.get("/review-queue").json()
    exported = client.get("/export/cleaned-catalog")
    assert latest["batch_id"] == second_batch["batch_id"]
    assert latest["batch_id"] != first_batch["batch_id"]
    assert latest["total_records"] == 2
    assert [record["cleaned_product_name"] for record in clean] == ["New Good"]
    assert [record["cleaned_product_name"] for record in review] == ["New Bad"]
    assert latest["attention_count"] == len(review) == 1
    assert "New Good" in exported.text
    assert "Old Product" not in exported.text
    app.dependency_overrides.clear()


def test_unresolved_invalid_record_cannot_be_human_approved_for_export():
    client, _ = make_client()
    payload = "product_name,price,currency,inventory\nCeramic Mug,11.50,USD,Not available\n"
    batch = client.post("/batches", files={"file": ("catalog.csv", payload, "text/csv")}).json()
    review_item = client.get(f"/batches/{batch['batch_id']}/review-items").json()[0]

    blocked = client.post(
        f"/review-items/{review_item['id']}/decision",
        json={"decision": "edited", "corrected_values": {}},
    )
    assert blocked.status_code == 409
    assert "inventory: invalid value" in blocked.json()["detail"]["validation_errors"]

    latest = client.get(f"/batches/{batch['batch_id']}").json()
    assert latest["publishable_count"] == 0
    assert latest["attention_count"] == 1
    assert len(client.get(f"/review-queue?batch_id={batch['batch_id']}").json()) == 1
    assert client.get(f"/export/cleaned-catalog?batch_id={batch['batch_id']}").status_code == 404

    fixed = client.post(
        f"/review-items/{review_item['id']}/decision",
        json={"decision": "edited", "corrected_values": {"cleaned_inventory": 7}},
    )
    assert fixed.status_code == 200
    assert fixed.json()["exportable"] is True
    assert fixed.json()["status"] == "Invalid"
    assert fixed.json()["review_status"] == "edited"

    exported = client.get(f"/export/cleaned-catalog?batch_id={batch['batch_id']}")
    assert exported.status_code == 200
    assert "Ceramic Mug" in exported.text
    app.dependency_overrides.clear()


def test_existing_reviewed_but_still_invalid_record_is_reclassified_as_attention():
    client, engine = make_client()
    payload = "product_name,price,currency,inventory\nCeramic Mug,11.50,USD,Not available\n"
    batch = client.post("/batches", files={"file": ("catalog.csv", payload, "text/csv")}).json()

    # Simulate a record approved under the older, overly permissive review rule.
    with Session(engine) as session:
        record = session.exec(select(CatalogRecord).where(CatalogRecord.batch_id == batch["batch_id"])).one()
        record.review_status = "edited"
        record.reviewed = True
        record.exportable = True
        session.add(record)
        session.commit()

    latest = client.get(f"/batches/{batch['batch_id']}").json()
    assert latest["publishable_count"] == 0
    assert latest["attention_count"] == 1
    queue = client.get(f"/review-queue?batch_id={batch['batch_id']}").json()
    assert len(queue) == 1
    assert queue[0]["exportable"] is False
    assert client.get(f"/export/cleaned-catalog?batch_id={batch['batch_id']}").status_code == 404
    app.dependency_overrides.clear()


def test_unsupported_upload_has_a_readable_error():
    client, _ = make_client()
    response = client.post("/batches", files={"file": ("catalog.txt", b"not,csv", "text/plain")})
    assert response.status_code == 400
    assert response.json()["detail"] == "Please upload a CSV file."

    header_only = client.post(
        "/batches",
        files={"file": ("header-only.csv", b"product_name,price,currency\n", "text/csv")},
    )
    assert header_only.status_code == 400
    assert header_only.json()["detail"] == "The uploaded CSV contains no data rows."

    malformed = client.post(
        "/batches",
        files={"file": ("malformed.csv", b'product_name,price\n"unterminated,10\n', "text/csv")},
    )
    assert malformed.status_code == 400
    assert malformed.json()["detail"].startswith("Unable to parse CSV:")
    app.dependency_overrides.clear()


def test_explicit_stale_batch_never_falls_through_to_latest_data():
    client, _ = make_client()
    payload = "product_name,price,currency\nCurrent Product,10,USD\n"
    current = client.post("/batches", files={"file": ("current.csv", payload, "text/csv")}).json()
    assert client.get(f"/schema-drift-report?batch_id={current['batch_id']}").status_code == 200

    for path in (
        "/processed-records?batch_id=99999",
        "/review-queue?batch_id=99999",
        "/batches/99999/review-items",
        "/schema-drift-report?batch_id=99999",
        "/export/cleaned-catalog?batch_id=99999",
        "/export/schema-drift-report?batch_id=99999",
    ):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["detail"] == "Batch not found."
    app.dependency_overrides.clear()
