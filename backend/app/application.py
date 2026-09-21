from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from .config import SETTINGS
from .domain import ProcessingResult
from .models import CatalogRecord, ProcessingRun, ReviewItem, SchemaDriftReport, SchemaMapping, UploadBatch
from .policy import (
    AUTOMATION_DUPLICATE,
    AUTOMATION_INVALID,
    AUTOMATION_NEEDS_REVIEW,
    AUTOMATION_TRUSTED,
    REVIEW_NOT_REQUIRED,
    REVIEW_PENDING,
    apply_publish_policy,
    requires_attention,
)
from .processing import CatalogProcessor, PandasCatalogProcessor


def _json(value: Any) -> str:
    def default(item: Any):
        if isinstance(item, Decimal):
            return float(item)
        if hasattr(item, "isoformat"):
            return item.isoformat()
        raise TypeError
    return json.dumps(value, default=default, sort_keys=True)


def _drift_severity(result: ProcessingResult) -> str:
    unresolved = sum(1 for mapping in result.mappings if mapping.canonical_field is None)
    score = len(result.missing_columns) * 2 + len(result.unexpected_columns) + unresolved * 2
    return "High" if score >= 6 else "Medium" if score >= 2 else "Low"


def _source_value(result: ProcessingResult, raw: dict[str, Any], canonical_field: str) -> Any:
    mapping = next(
        (item for item in result.mappings if item.auto_applied and item.canonical_field == canonical_field),
        None,
    )
    return raw.get(mapping.source_field if mapping else canonical_field)


def process_catalog(
    filename: str,
    payload: bytes,
    session: Session,
    processor: CatalogProcessor | None = None,
    merchant_id: int | None = None,
    merchant_aliases: dict[str, str] | None = None,
    default_currency: str | None = None,
) -> dict[str, Any]:
    result = (processor or PandasCatalogProcessor()).process(payload, merchant_aliases, default_currency)
    batch = UploadBatch(
        filename=filename,
        merchant_id=merchant_id,
        total_records=len(result.records),
        default_currency=result.default_currency,
    )
    session.add(batch)
    session.flush()
    run = ProcessingRun(
        batch_id=batch.id,
        processor_type="local",
        status="completed",
        started_at=result.started_at,
        completed_at=result.completed_at,
        config_snapshot=_json({"thresholds": SETTINGS.__dict__, "default_currency": result.default_currency}),
    )
    session.add(run)
    session.flush()
    for mapping in result.mappings:
        session.add(SchemaMapping(run_id=run.id, **mapping.model_dump(mode="json")))

    stored: list[CatalogRecord] = []
    for processed in result.records:
        values = processed.canonical_values
        raw = processed.raw_values
        issues = list(processed.validation_errors)
        for component in processed.quality.components.values():
            issues.extend(component.reasons)
        issues = list(dict.fromkeys(issues))
        if processed.duplicate:
            issues.append("Exact duplicate detected" if processed.duplicate.exact else "Possible fuzzy duplicate candidate")
        invalid = bool(processed.validation_errors)
        duplicate = bool(processed.duplicate and processed.duplicate.exact)
        status = (
            AUTOMATION_INVALID if invalid else
            AUTOMATION_DUPLICATE if duplicate else
            AUTOMATION_TRUSTED if processed.route == "publishable" else
            AUTOMATION_NEEDS_REVIEW
        )
        confidence = processed.quality.overall
        record = CatalogRecord(
            batch_id=batch.id,
            row_index=processed.row_index,
            raw_values=_json(raw), canonical_values=_json(values),
            normalization_trace=_json([trace.model_dump(mode="json") for trace in processed.traces]),
            quality_components=_json({key: value.model_dump(mode="json") for key, value in processed.quality.components.items()}),
            validation_errors=_json(processed.validation_errors),
            sku=values.get("sku"),
            original_product_name=str(_source_value(result, raw, "product_name") or ""),
            original_category=str(_source_value(result, raw, "category") or ""),
            original_price=str(_source_value(result, raw, "price") or ""),
            original_inventory=str(_source_value(result, raw, "inventory") or ""),
            original_tags=str(_source_value(result, raw, "tags") or ""), cleaned_product_name=values.get("product_name"),
            cleaned_description=values.get("description"), cleaned_category=values.get("category"),
            cleaned_price=float(values["price"]) if values.get("price") is not None else None,
            cleaned_currency=values.get("currency"), cleaned_inventory=values.get("inventory"),
            cleaned_tags=", ".join(values.get("tags") or []), automation_confidence=confidence,
            confidence_score=round(confidence * 100, 1), status=status,
            recommended_action="Publish" if status == AUTOMATION_TRUSTED else "Block from export" if status in {AUTOMATION_INVALID, AUTOMATION_DUPLICATE} else "Review record",
            issue_reasons=_json(issues), severity="High" if invalid else "Medium" if status != AUTOMATION_TRUSTED else "Low",
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

    batch.auto_approved_count = sum(record.status == AUTOMATION_TRUSTED for record in stored)
    batch.needs_review_count = sum(record.status == AUTOMATION_NEEDS_REVIEW for record in stored)
    batch.duplicate_count = sum(record.status == AUTOMATION_DUPLICATE for record in stored)
    batch.invalid_count = sum(record.status == AUTOMATION_INVALID for record in stored)
    batch.attention_count = sum(requires_attention(record) for record in stored)
    batch.average_confidence = round(sum(record.confidence_score for record in stored) / max(1, len(stored)), 1)
    batch.schema_drift_detected = bool(result.missing_columns or result.unexpected_columns)
    suggested = {mapping.source_field: mapping.canonical_field for mapping in result.mappings if mapping.canonical_field}
    applied = {mapping.source_field: mapping.canonical_field for mapping in result.mappings if mapping.auto_applied}
    unresolved = {mapping.source_field: "human_review" for mapping in result.mappings if not mapping.auto_applied}
    report = SchemaDriftReport(
        batch_id=batch.id, profiles=_json([profile.model_dump(mode="json") for profile in result.profiles]),
        missing_columns=_json(result.missing_columns), unexpected_columns=_json(result.unexpected_columns),
        suggested_mappings=_json(suggested), auto_applied_mappings=_json(applied),
        unresolved_mappings=_json(unresolved), drift_severity=_drift_severity(result),
    )
    session.add_all([batch, report])
    session.commit()
    return batch_summary(batch, report, result.mappings)


def batch_summary(batch: UploadBatch, report: SchemaDriftReport, mappings: list[Any] | None = None) -> dict[str, Any]:
    schema_report = {
        "missing_columns": json.loads(report.missing_columns), "unexpected_columns": json.loads(report.unexpected_columns),
        "suggested_mappings": json.loads(report.suggested_mappings), "auto_applied_mappings": json.loads(report.auto_applied_mappings),
        "unresolved_mappings": json.loads(report.unresolved_mappings), "drift_severity": report.drift_severity,
        "profiles": json.loads(report.profiles),
    }
    return {
        "upload_id": batch.id, "batch_id": batch.id, "filename": batch.filename, "total_records": batch.total_records,
        "auto_approved_count": batch.auto_approved_count, "needs_review_count": batch.needs_review_count,
        "duplicate_count": batch.duplicate_count, "invalid_count": batch.invalid_count,
        "attention_count": batch.attention_count,
        "average_confidence": batch.average_confidence, "schema_drift_detected": batch.schema_drift_detected,
        "default_currency": batch.default_currency,
        "status": batch.status, "schema_report": schema_report,
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
        {"source_field": item.source_field, "canonical_field": item.canonical_field, "confidence": item.confidence,
         "method": item.method, "auto_applied": item.auto_applied}
        for item in mappings
    ]
    return batch_summary(batch, report, serialized)
