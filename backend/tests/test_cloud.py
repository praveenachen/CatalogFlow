import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.application import OrchestrationError, orchestrate_catalog, refresh_curated_artifact, refresh_processing_run
from app.config import RuntimeSettings
from app.domain import ProcessingRequest, ProcessingResult, ProcessorStatus, ProcessorSubmission, RunStatus
from app.ingestion import CatalogIngestionError
from app.models import CatalogArtifact, CatalogRecord, ProcessingRun, UploadBatch
from app.pipeline_contract import gold_rows, result_metrics, silver_rows
from app.processing import CatalogProcessor, DatabricksCatalogProcessor, PandasCatalogProcessor
from app.reviews import apply_review_decision
from app.runtime import RuntimeConfigurationError, build_processor, build_storage
from app.storage import LocalCatalogStorage, S3CatalogStorage


def memory_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_local_catalog_storage_is_immutable_for_raw_data(tmp_path):
    storage = LocalCatalogStorage(tmp_path)
    stored = storage.save_raw(b"a,b\n1,2\n", batch_id=7, merchant_id=3, filename="merchant.csv")
    assert stored.key == "raw/3/7/source.csv"
    assert storage.exists(stored.uri)
    assert storage.read(stored.uri) == b"a,b\n1,2\n"
    assert storage.save_raw(b"a,b\n1,2\n", 7, 3, "merchant.csv").checksum == stored.checksum
    with pytest.raises(FileExistsError):
        storage.save_raw(b"different", 7, 3, "merchant.csv")


def test_repeated_upload_payloads_keep_checksum_identity_without_path_collision(tmp_path):
    storage = LocalCatalogStorage(tmp_path)
    payload = b"product_name,price,currency\nShoe,10,USD\n"
    first = storage.save_raw(payload, batch_id=1, merchant_id=None, filename="first.csv")
    second = storage.save_raw(payload, batch_id=2, merchant_id=None, filename="second.csv")
    assert first.checksum == second.checksum
    assert first.uri != second.uri
    assert storage.read(first.uri) == storage.read(second.uri) == payload


class FakeClientError(Exception):
    def __init__(self, code: str):
        self.response = {"Error": {"Code": code}}


class FakeS3Client:
    exceptions = SimpleNamespace(ClientError=FakeClientError)

    def __init__(self):
        self.objects = {}
        self.put_calls = []

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise FakeClientError("404")
        return {}

    def put_object(self, **kwargs):
        if kwargs.get("IfNoneMatch") == "*" and (kwargs["Bucket"], kwargs["Key"]) in self.objects:
            raise FakeClientError("PreconditionFailed")
        self.put_calls.append(kwargs)
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


def test_s3_storage_uses_private_deterministic_keys_and_metadata():
    client = FakeS3Client()
    storage = S3CatalogStorage("private-catalogs", "ca-central-1", client=client)
    stored = storage.save_raw(b"sku,name\n1,Shoe\n", 12, 4, "input.csv")
    call = client.put_calls[0]
    assert stored.uri == "s3://private-catalogs/raw/4/12/source.csv"
    assert call["Key"] == "raw/4/12/source.csv"
    assert call["ServerSideEncryption"] == "AES256"
    assert call["IfNoneMatch"] == "*"
    assert "ACL" not in call
    assert call["Metadata"]["sha256"] == stored.checksum
    assert storage.read(stored.uri) == b"sku,name\n1,Shoe\n"
    with pytest.raises(FileExistsError):
        storage.save_raw(b"different", 12, 4, "input.csv")


def test_runtime_selection_is_explicit_and_never_silently_falls_back(monkeypatch, tmp_path):
    local = RuntimeSettings(local_storage_root=tmp_path)
    assert isinstance(build_storage(local), LocalCatalogStorage)
    assert isinstance(build_processor(local), PandasCatalogProcessor)
    with pytest.raises(RuntimeConfigurationError):
        build_processor(RuntimeSettings(catalog_processor="databricks", catalog_storage="local", databricks_job_id=10))

    sentinel = object()
    monkeypatch.setattr("app.runtime.DatabricksCatalogProcessor", lambda **kwargs: sentinel)
    cloud = RuntimeSettings(catalog_processor="databricks", catalog_storage="s3", aws_s3_bucket="bucket", databricks_job_id=10)
    assert build_processor(cloud) is sentinel


class FakeJobs:
    def __init__(self):
        self.submission = None
        self.state = SimpleNamespace(life_cycle_state="RUNNING", result_state=None, state_message=None)

    def run_now(self, **kwargs):
        self.submission = kwargs
        return SimpleNamespace(run_id=9988)

    def get_run(self, run_id):
        assert run_id == 9988
        return SimpleNamespace(state=self.state)


def test_databricks_submission_and_lifecycle_mapping():
    jobs = FakeJobs()
    processor = DatabricksCatalogProcessor(123, workspace_client=SimpleNamespace(jobs=jobs))
    request = ProcessingRequest(
        batch_id=8,
        merchant_id=2,
        raw_uri="s3://bucket/raw/2/8/source.csv",
        processed_uri="s3://bucket/processed/2/8/silver.delta",
        curated_uri="s3://bucket/curated/2/8/gold.delta",
    )
    submission = processor.submit(request)
    assert submission.external_run_id == "9988"
    assert submission.status == RunStatus.submitted
    assert jobs.submission["job_id"] == 123
    assert jobs.submission["job_parameters"]["raw_uri"] == request.raw_uri
    assert processor.refresh("9988").status == RunStatus.running

    jobs.state = SimpleNamespace(life_cycle_state="TERMINATED", result_state="FAILED", state_message="task failed")
    failed = processor.refresh("9988")
    assert failed.status == RunStatus.failed
    assert failed.error_code == "FAILED"
    assert failed.error_message == "task failed"

    jobs.state = SimpleNamespace(life_cycle_state="TERMINATED", result_state="SUCCESS", state_message="done")
    jobs.get_run_output = lambda run_id: SimpleNamespace(
        notebook_output=SimpleNamespace(result=json.dumps({"quality_metrics": {"total_records": 7}}))
    )
    completed = processor.refresh("9988")
    assert completed.status == RunStatus.completed
    assert completed.result_metadata["quality_metrics"]["total_records"] == 7

    jobs.state = SimpleNamespace(life_cycle_state="CANCELED", result_state="CANCELED", state_message="cancelled")
    assert processor.refresh("9988").status == RunStatus.cancelled


class AsyncProcessor(CatalogProcessor):
    processor_type = "databricks"
    asynchronous = True

    def process(self, payload, merchant_aliases=None, default_currency=None) -> ProcessingResult:
        raise NotImplementedError

    def submit(self, request):
        return ProcessorSubmission(status=RunStatus.submitted, external_run_id="cloud-42")

    def refresh(self, external_run_id):
        return ProcessorStatus(status=RunStatus.running)


class FailingProcessor(AsyncProcessor):
    def submit(self, request):
        raise RuntimeError("workspace unavailable")


class FailedRunProcessor(AsyncProcessor):
    def refresh(self, external_run_id):
        return ProcessorStatus(
            status=RunStatus.failed,
            error_code="TASK_FAILED",
            error_message="Delta write failed",
            result_metadata={"lifecycle_state": "TERMINATED", "result_state": "FAILED"},
        )


def test_async_run_id_is_persisted_and_submission_failure_preserves_raw(tmp_path):
    session = memory_session()
    storage = LocalCatalogStorage(tmp_path)
    outcome = orchestrate_catalog("input.csv", b"product_name,price,currency\nShoe,10,USD\n", session, AsyncProcessor(), storage)
    run = session.get(ProcessingRun, outcome["run_id"])
    assert run.external_run_id == "cloud-42"
    assert run.status == "SUBMITTED"
    assert storage.exists(run.raw_uri)

    with pytest.raises(OrchestrationError) as error:
        orchestrate_catalog("failed.csv", b"product_name,price,currency\nBoot,20,USD\n", session, FailingProcessor(), storage)
    failed_run = session.get(ProcessingRun, error.value.run_id)
    failed_batch = session.get(UploadBatch, error.value.batch_id)
    assert failed_run.status == "FAILED"
    assert failed_run.error_code == "PROCESSOR_SUBMISSION_FAILED"
    assert storage.exists(failed_run.raw_uri)
    assert failed_batch.status == "FAILED"


def test_invalid_local_input_is_recorded_failed_and_raw_is_preserved(tmp_path):
    session = memory_session()
    storage = LocalCatalogStorage(tmp_path)
    with pytest.raises(CatalogIngestionError):
        orchestrate_catalog("empty.csv", b"", session, PandasCatalogProcessor(), storage)
    run = session.exec(select(ProcessingRun).order_by(ProcessingRun.id.desc())).first()
    assert run.status == "FAILED"
    assert run.error_code == "INVALID_INPUT"
    assert storage.exists(run.raw_uri)


def test_terminal_job_failure_is_persisted_without_losing_raw(tmp_path):
    session = memory_session()
    storage = LocalCatalogStorage(tmp_path)
    outcome = orchestrate_catalog(
        "input.csv",
        b"product_name,price,currency\nShoe,10,USD\n",
        session,
        FailedRunProcessor(),
        storage,
    )
    run = refresh_processing_run(session, outcome["run_id"], FailedRunProcessor())
    assert run.status == "FAILED"
    assert run.error_code == "TASK_FAILED"
    assert run.error_message == "Delta write failed"
    assert storage.exists(run.raw_uri)
    assert session.get(UploadBatch, outcome["batch_id"]).status == "FAILED"


def test_local_medallion_artifacts_enforce_gold_policy_and_preserve_confidence(tmp_path):
    session = memory_session()
    storage = LocalCatalogStorage(tmp_path)
    sample = Path(__file__).parents[2] / "frontend" / "public" / "sample-messy-catalog.csv"
    outcome = orchestrate_catalog(sample.name, sample.read_bytes(), session, PandasCatalogProcessor(), storage)
    artifacts = session.exec(select(CatalogArtifact).where(CatalogArtifact.batch_id == outcome["batch_id"])).all()
    by_layer = {artifact.layer: artifact for artifact in artifacts}
    silver = [json.loads(line) for line in storage.read(by_layer["silver"].object_uri).splitlines()]
    gold = [json.loads(line) for line in storage.read(by_layer["gold"].object_uri).splitlines()]
    assert len(silver) == 20
    assert len(gold) == 16
    assert all(record["review_status"] == "not_required" for record in gold)
    assert not any(record["automation_status"] in {"Invalid", "Duplicate", "Needs Review"} for record in gold)

    invalid = session.exec(
        select(CatalogRecord).where(CatalogRecord.batch_id == outcome["batch_id"], CatalogRecord.status == "Invalid")
    ).first()
    original_confidence = invalid.automation_confidence
    apply_review_decision(session, invalid, "edited", {"cleaned_inventory": 11})
    refreshed = refresh_curated_artifact(session, storage, outcome["batch_id"])
    reviewed_gold = [json.loads(line) for line in storage.read(refreshed.uri).splitlines()]
    reviewed = next(record for record in reviewed_gold if record["sku"] == invalid.sku)
    assert len(reviewed_gold) == 17
    assert reviewed["review_status"] == "edited"
    assert reviewed["automation_confidence"] == original_confidence


def test_databricks_projection_contract_matches_local_pipeline_semantics():
    sample = Path(__file__).parents[2] / "frontend" / "public" / "sample-messy-catalog.csv"
    result = PandasCatalogProcessor().process(sample.read_bytes())
    silver = silver_rows(result, batch_id=9, merchant_id=2)
    gold = gold_rows(result, batch_id=9, merchant_id=2)
    metrics = result_metrics(result)
    assert len(silver) == 20
    assert len(gold) == 16
    assert metrics == {
        **metrics,
        "total_records": 20,
        "auto_approved": 16,
        "needs_review": 1,
        "duplicate_candidates": 1,
        "invalid": 2,
        "attention_required": 4,
        "publishable": 16,
    }
    assert all(row["automation_status"] == "Auto-approved" for row in gold)
    assert all(row["review_status"] == "not_required" for row in gold)
