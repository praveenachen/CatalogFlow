import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import CatalogRecord


def make_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    return TestClient(app), engine


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
