from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from .config import SETTINGS
from .domain import ProcessingRequest, ProcessingResult, RunStatus
from .ingestion import CatalogIngestionError
from .medallion import gold_payload, quality_metrics, silver_payload
from .pipeline_contract import automation_status, schema_drift_summary
from .models import (
    CatalogArtifact,
    CatalogRecord,
    ProcessingRun,
    ReviewItem,
    SchemaDriftReport,
    SchemaMapping,
    UploadBatch,
)
from .policy import (
    AUTOMATION_DUPLICATE,
    AUTOMATION_INVALID,
    AUTOMATION_NEEDS_REVIEW,
    AUTOMATION_TRUSTED,
    REVIEW_NOT_REQUIRED,
    REVIEW_PENDING,
    apply_publish_policy,
    is_publishable,
    requires_attention,
)
from .processing import CatalogProcessor
from .storage import CatalogStorage, StoredObject


class OrchestrationError(RuntimeError):
    def __init__(self, message: str, batch_id: int, run_id: int, error_code: str) -> None:
        super().__init__(message)
        self.batch_id = batch_id
        self.run_id = run_id
        self.error_code = error_code


def _json(value: Any) -> str:
    def default(item: Any):
        if isinstance(item, Decimal):
            return float(item)
        if hasattr(item, "isoformat"):
            return item.isoformat()
        raise TypeError

    return json.dumps(value, default=default, sort_keys=True)


def _source_value(result: ProcessingResult, raw: dict[str, Any], canonical_field: str) -> Any:
    mapping = next(
        (item for item in result.mappings if item.auto_applied and item.canonical_field == canonical_field),
        None,
    )
    return raw.get(mapping.source_field if mapping else canonical_field)


def _add_artifact(session: Session, stored: StoredObject, layer: str) -> None:
    session.add(
        CatalogArtifact(
            batch_id=stored.batch_id,
            merchant_id=stored.merchant_id,
            layer=layer,
            object_uri=stored.uri,
            object_key=stored.key,
            checksum=stored.checksum,
            size_bytes=stored.size_bytes,
            created_at=stored.uploaded_at,
        )
    )


def _mark_failed(session: Session, batch_id: int, run_id: int, code: str, message: str) -> None:
    session.rollback()
    batch = session.get(UploadBatch, batch_id)
    run = session.get(ProcessingRun, run_id)
    now = datetime.now(timezone.utc)
    if batch:
        batch.status = RunStatus.failed.value
        session.add(batch)
    if run:
        run.status = RunStatus.failed.value
        run.completed_at = now
        run.error_code = code
        run.error_message = message[:2000]
        session.add(run)
    session.commit()


def orchestrate_catalog(
    filename: str,
    payload: bytes,
    session: Session,
    processor: CatalogProcessor,
    storage: CatalogStorage,
    merchant_id: int | None = None,
    default_currency: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    batch = UploadBatch(
        filename=filename,
        merchant_id=merchant_id,
        total_records=0,
        default_currency=default_currency.upper() if default_currency else None,
        status=RunStatus.pending.value,
    )
    session.add(batch)
    session.flush()
    processed_name = "silver.delta" if processor.asynchronous else "silver.jsonl"
    curated_name = "gold.delta" if processor.asynchronous else "gold.jsonl"
    processed_uri = storage.location("processed", batch.id, merchant_id, processed_name)
    curated_uri = storage.location("curated", batch.id, merchant_id, curated_name)
    run = ProcessingRun(
        batch_id=batch.id,
        processor_type=processor.processor_type,
        status=RunStatus.pending.value,
        started_at=now,
        processed_uri=processed_uri,
        curated_uri=curated_uri,
        config_snapshot=_json({"thresholds": SETTINGS.__dict__, "default_currency": batch.default_currency}),
    )
    session.add(run)
    session.commit()
    session.refresh(batch)
    session.refresh(run)

    try:
        raw = storage.save_raw(payload, batch.id, merchant_id, filename)
        run.raw_uri = raw.uri
        _add_artifact(session, raw, "bronze")
        session.add(run)
        session.commit()
    except Exception as exc:
        _mark_failed(session, batch.id, run.id, "STORAGE_WRITE_FAILED", str(exc))
        raise OrchestrationError("Raw catalog storage failed; processing was not submitted.", batch.id, run.id, "STORAGE_WRITE_FAILED") from exc

    request = ProcessingRequest(
        batch_id=batch.id,
        merchant_id=merchant_id,
        raw_uri=run.raw_uri,
        processed_uri=processed_uri,
        curated_uri=curated_uri,
        default_currency=batch.default_currency,
        payload=payload if not processor.asynchronous else None,
    )
    try:
        submission = processor.submit(request)
    except CatalogIngestionError as exc:
        _mark_failed(session, batch.id, run.id, "INVALID_INPUT", str(exc))
        raise
    except Exception as exc:
        _mark_failed(session, batch.id, run.id, "PROCESSOR_SUBMISSION_FAILED", str(exc))
        raise OrchestrationError("Catalog processor submission failed.", batch.id, run.id, "PROCESSOR_SUBMISSION_FAILED") from exc

    run.external_run_id = submission.external_run_id
    run.status = submission.status.value
    batch.status = submission.status.value
    if submission.result is None:
        session.add_all([run, batch])
        session.commit()
        return upload_response(batch, run, None)

    try:
        records, report = _persist_result(session, batch, run, submission.result)
        silver = storage.save_processed(silver_payload(records), batch.id, merchant_id)
        gold = storage.save_curated(gold_payload(records), batch.id, merchant_id)
        metrics = quality_metrics(batch, [profile.model_dump(mode="json") for profile in submission.result.profiles])
        report_object = storage.save_report(_json(metrics).encode("utf-8"), batch.id, merchant_id)
        _add_artifact(session, silver, "silver")
        _add_artifact(session, gold, "gold")
        _add_artifact(session, report_object, "reports")
        run.processed_uri = silver.uri
        run.curated_uri = gold.uri
        run.status = RunStatus.completed.value
        run.completed_at = submission.result.completed_at
        batch.status = RunStatus.completed.value
        session.add_all([run, batch])
        session.commit()
        return upload_response(batch, run, report, submission.result.mappings)
    except Exception as exc:
        _mark_failed(session, batch.id, run.id, "PROCESSING_FAILED", str(exc))
        raise OrchestrationError("Catalog processing failed; raw data remains available.", batch.id, run.id, "PROCESSING_FAILED") from exc


def _persist_result(
    session: Session,
    batch: UploadBatch,
    run: ProcessingRun,
    result: ProcessingResult,
) -> tuple[list[CatalogRecord], SchemaDriftReport]:
    for mapping in result.mappings:
        session.add(SchemaMapping(run_id=run.id, **mapping.model_dump(mode="json")))
    stored: list[CatalogRecord] = []
    for processed in result.records:
        values, raw = processed.canonical_values, processed.raw_values
        issues = list(processed.validation_errors)
        for component in processed.quality.components.values():
            issues.extend(component.reasons)
        issues = list(dict.fromkeys(issues))
        if processed.duplicate:
            issues.append("Exact duplicate detected" if processed.duplicate.exact else "Possible fuzzy duplicate candidate")
        invalid = bool(processed.validation_errors)
        status = automation_status(processed)
        confidence = processed.quality.overall
        record = CatalogRecord(
            batch_id=batch.id,
            row_index=processed.row_index,
            raw_values=_json(raw),
            canonical_values=_json(values),
            normalization_trace=_json([trace.model_dump(mode="json") for trace in processed.traces]),
            quality_components=_json({key: value.model_dump(mode="json") for key, value in processed.quality.components.items()}),
            validation_errors=_json(processed.validation_errors),
            sku=values.get("sku"),
            original_product_name=str(_source_value(result, raw, "product_name") or ""),
            original_category=str(_source_value(result, raw, "category") or ""),
            original_price=str(_source_value(result, raw, "price") or ""),
            original_inventory=str(_source_value(result, raw, "inventory") or ""),
            original_tags=str(_source_value(result, raw, "tags") or ""),
            cleaned_product_name=values.get("product_name"),
            cleaned_description=values.get("description"),
            cleaned_category=values.get("category"),
            cleaned_price=float(values["price"]) if values.get("price") is not None else None,
            cleaned_currency=values.get("currency"),
            cleaned_inventory=values.get("inventory"),
            cleaned_tags=", ".join(values.get("tags") or []),
            automation_confidence=confidence,
            confidence_score=round(confidence * 100, 1),
            status=status,
            recommended_action="Publish" if status == AUTOMATION_TRUSTED else "Block from export" if status in {AUTOMATION_INVALID, AUTOMATION_DUPLICATE} else "Review record",
            issue_reasons=_json(issues),
            severity="High" if invalid else "Medium" if status != AUTOMATION_TRUSTED else "Low",
            review_status=REVIEW_NOT_REQUIRED if status == AUTOMATION_TRUSTED else REVIEW_PENDING,
            exportable=False,
            duplicate_of_record_id=(stored[processed.duplicate.matched_row_index].id if processed.duplicate else None),
            duplicate_method=processed.duplicate.method if processed.duplicate else None,
            duplicate_confidence=processed.duplicate.confidence if processed.duplicate else None,
        )
        apply_publish_policy(record)
        session.add(record)
        session.flush()
        stored.append(record)
        if status != AUTOMATION_TRUSTED:
            session.add(ReviewItem(record_id=record.id, reason="; ".join(issues) or "Quality threshold not met", automated_confidence=confidence))

    drift_count, severity = schema_drift_summary(result)
    batch.total_records = len(stored)
    batch.auto_approved_count = sum(record.status == AUTOMATION_TRUSTED for record in stored)
    batch.needs_review_count = sum(record.status == AUTOMATION_NEEDS_REVIEW for record in stored)
    batch.duplicate_count = sum(record.status == AUTOMATION_DUPLICATE for record in stored)
    batch.invalid_count = sum(record.status == AUTOMATION_INVALID for record in stored)
    batch.attention_count = sum(requires_attention(record) for record in stored)
    batch.publishable_count = sum(is_publishable(record) for record in stored)
    batch.average_confidence = round(sum(record.confidence_score for record in stored) / max(1, len(stored)), 1)
    batch.schema_drift_count = drift_count
    batch.schema_drift_detected = batch.schema_drift_count > 0
    batch.schema_drift_severity = severity
    profiles = [profile.model_dump(mode="json") for profile in result.profiles]
    batch.quality_metrics = _json(quality_metrics(batch, profiles))
    suggested = {mapping.source_field: mapping.canonical_field for mapping in result.mappings if mapping.canonical_field}
    applied = {mapping.source_field: mapping.canonical_field for mapping in result.mappings if mapping.auto_applied}
    unresolved = {mapping.source_field: "human_review" for mapping in result.mappings if not mapping.auto_applied}
    report = SchemaDriftReport(
        batch_id=batch.id,
        profiles=_json(profiles),
        missing_columns=_json(result.missing_columns),
        unexpected_columns=_json(result.unexpected_columns),
        suggested_mappings=_json(suggested),
        auto_applied_mappings=_json(applied),
        unresolved_mappings=_json(unresolved),
        drift_severity=severity,
    )
    session.add_all([batch, report])
    session.flush()
    return stored, report


def refresh_processing_run(session: Session, run_id: int, processor: CatalogProcessor) -> ProcessingRun:
    run = session.get(ProcessingRun, run_id)
    if not run:
        raise LookupError("Processing run not found.")
    if run.processor_type != processor.processor_type:
        raise ValueError("Configured processor does not match this processing run.")
    if run.status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
        return run
    if not run.external_run_id:
        raise ValueError("Processing run has no external run identifier.")
    try:
        state = processor.refresh(run.external_run_id)
    except Exception as exc:
        _mark_failed(session, run.batch_id, run.id, "STATUS_REFRESH_FAILED", str(exc))
        return session.get(ProcessingRun, run.id)
    run.status = state.status.value
    run.error_code = state.error_code
    run.error_message = state.error_message
    run.result_metadata = _json(state.result_metadata)
    batch = session.get(UploadBatch, run.batch_id)
    if batch:
        batch.status = state.status.value
        metrics = state.result_metadata.get("quality_metrics", {})
        _apply_external_metrics(batch, metrics)
        session.add(batch)
    if state.status in {RunStatus.completed, RunStatus.failed, RunStatus.cancelled}:
        run.completed_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def refresh_curated_artifact(session: Session, storage: CatalogStorage, batch_id: int) -> StoredObject:
    batch = session.get(UploadBatch, batch_id)
    if not batch:
        raise LookupError("Batch not found.")
    records = session.exec(select(CatalogRecord).where(CatalogRecord.batch_id == batch_id).order_by(CatalogRecord.id)).all()
    run = session.exec(select(ProcessingRun).where(ProcessingRun.batch_id == batch_id).order_by(ProcessingRun.id.desc())).first()
    filename = "reviewed-gold.jsonl" if run and run.processor_type == "databricks" else "gold.jsonl"
    try:
        stored = storage.save_curated(gold_payload(records), batch.id, batch.merchant_id, filename=filename)
    except Exception as exc:
        if run:
            _mark_failed(session, batch.id, run.id, "CURATED_STORAGE_FAILED", str(exc))
            raise OrchestrationError("Review was saved, but the curated artifact refresh failed.", batch.id, run.id, "CURATED_STORAGE_FAILED") from exc
        raise
    _add_artifact(session, stored, "gold_review" if filename.startswith("reviewed") else "gold")
    batch.publishable_count = sum(is_publishable(record) for record in records)
    metrics = json.loads(batch.quality_metrics or "{}")
    metrics["publishable"] = batch.publishable_count
    metrics["attention_required"] = batch.attention_count
    batch.quality_metrics = _json(metrics)
    session.add(batch)
    session.commit()
    return stored


def _apply_external_metrics(batch: UploadBatch, metrics: dict[str, Any]) -> None:
    fields = {
        "total_records": "total_records",
        "auto_approved": "auto_approved_count",
        "needs_review": "needs_review_count",
        "invalid": "invalid_count",
        "duplicate_candidates": "duplicate_count",
        "attention_required": "attention_count",
        "publishable": "publishable_count",
        "average_automation_confidence": "average_confidence",
        "schema_drift_count": "schema_drift_count",
        "schema_drift_severity": "schema_drift_severity",
    }
    for source, target in fields.items():
        if source in metrics:
            setattr(batch, target, metrics[source])
    if metrics:
        batch.quality_metrics = _json(metrics)
        batch.schema_drift_detected = batch.schema_drift_count > 0


def upload_response(
    batch: UploadBatch,
    run: ProcessingRun,
    report: SchemaDriftReport | None,
    mappings: list[Any] | None = None,
) -> dict[str, Any]:
    response = batch_summary(batch, report, mappings)
    response.update(
        run_id=run.id,
        processor_type=run.processor_type,
        processing_status=run.status,
        external_run_id=run.external_run_id,
        raw_uri=run.raw_uri,
        processed_uri=run.processed_uri,
        curated_uri=run.curated_uri,
    )
    return response


def batch_summary(batch: UploadBatch, report: SchemaDriftReport | None, mappings: list[Any] | None = None) -> dict[str, Any]:
    schema_report = {
        "missing_columns": json.loads(report.missing_columns) if report else [],
        "unexpected_columns": json.loads(report.unexpected_columns) if report else [],
        "suggested_mappings": json.loads(report.suggested_mappings) if report else {},
        "auto_applied_mappings": json.loads(report.auto_applied_mappings) if report else {},
        "unresolved_mappings": json.loads(report.unresolved_mappings) if report else {},
        "drift_severity": report.drift_severity if report else batch.schema_drift_severity,
        "profiles": json.loads(report.profiles) if report else [],
    }
    return {
        "upload_id": batch.id,
        "batch_id": batch.id,
        "filename": batch.filename,
        "uploaded_at": batch.uploaded_at,
        "total_records": batch.total_records,
        "auto_approved_count": batch.auto_approved_count,
        "needs_review_count": batch.needs_review_count,
        "duplicate_count": batch.duplicate_count,
        "invalid_count": batch.invalid_count,
        "attention_count": batch.attention_count,
        "publishable_count": batch.publishable_count,
        "excluded_count": max(0, batch.total_records - batch.publishable_count),
        "average_confidence": batch.average_confidence,
        "schema_drift_detected": batch.schema_drift_detected,
        "schema_drift_count": batch.schema_drift_count,
        "schema_drift_severity": batch.schema_drift_severity,
        "default_currency": batch.default_currency,
        "status": batch.status,
        "quality_metrics": json.loads(batch.quality_metrics or "{}"),
        "schema_report": schema_report,
        "mappings": [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in (mappings or [])],
    }


def load_batch_summary(session: Session, batch_id: int) -> dict[str, Any] | None:
    batch = session.get(UploadBatch, batch_id)
    if not batch:
        return None
    report = session.exec(select(SchemaDriftReport).where(SchemaDriftReport.batch_id == batch_id)).first()
    run = session.exec(select(ProcessingRun).where(ProcessingRun.batch_id == batch_id).order_by(ProcessingRun.id.desc())).first()
    mappings = session.exec(select(SchemaMapping).where(SchemaMapping.run_id == run.id)).all() if run else []
    serialized = [
        {"source_field": item.source_field, "canonical_field": item.canonical_field, "confidence": item.confidence, "method": item.method, "auto_applied": item.auto_applied}
        for item in mappings
    ]
    # Recompute publish/attention counts from current record state so existing
    # batches immediately reflect tightened publishability rules after upgrades.
    records = session.exec(
        select(CatalogRecord).where(CatalogRecord.batch_id == batch_id).order_by(CatalogRecord.id)
    ).all()
    current_publishable = sum(is_publishable(record) for record in records)
    current_attention = sum(requires_attention(record) for record in records)

    response = batch_summary(batch, report, serialized)
    response["publishable_count"] = current_publishable
    response["attention_count"] = current_attention
    response["excluded_count"] = max(0, batch.total_records - current_publishable)
    response["quality_metrics"] = {
        **response.get("quality_metrics", {}),
        "publishable": current_publishable,
        "attention_required": current_attention,
    }
    if run:
        response.update(
            run_id=run.id,
            processor_type=run.processor_type,
            processing_status=run.status,
            external_run_id=run.external_run_id,
            raw_uri=run.raw_uri,
            processed_uri=run.processed_uri,
            curated_uri=run.curated_uri,
        )
    return response


def processing_run_response(run: ProcessingRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "batch_id": run.batch_id,
        "processor_type": run.processor_type,
        "external_run_id": run.external_run_id,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "raw_uri": run.raw_uri,
        "processed_uri": run.processed_uri,
        "curated_uri": run.curated_uri,
        "result_metadata": json.loads(run.result_metadata or "{}"),
    }
