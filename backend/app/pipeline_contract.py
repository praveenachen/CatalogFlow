from __future__ import annotations

from typing import Any

from .domain import ProcessedRecord, ProcessingResult
from .policy import AUTOMATION_DUPLICATE, AUTOMATION_INVALID, AUTOMATION_NEEDS_REVIEW, AUTOMATION_TRUSTED, REVIEW_NOT_REQUIRED, REVIEW_PENDING


def schema_drift_summary(result: ProcessingResult) -> tuple[int, str]:
    """Return the shared drift count/severity contract for local and cloud runs."""
    unresolved = sum(1 for mapping in result.mappings if mapping.canonical_field is None)
    drift_count = len(result.missing_columns) + len(result.unexpected_columns)
    drift_score = len(result.missing_columns) * 2 + len(result.unexpected_columns) + unresolved * 2
    severity = "High" if drift_score >= 6 else "Medium" if drift_score >= 2 else "Low"
    return drift_count, severity


def automation_status(record: ProcessedRecord) -> str:
    if record.validation_errors:
        return AUTOMATION_INVALID
    if record.duplicate and record.duplicate.exact:
        return AUTOMATION_DUPLICATE
    return AUTOMATION_TRUSTED if record.route == "publishable" else AUTOMATION_NEEDS_REVIEW


def silver_rows(result: ProcessingResult, batch_id: int, merchant_id: int | None) -> list[dict[str, Any]]:
    rows = []
    for record in result.records:
        status = automation_status(record)
        rows.append(
            {
                "batch_id": batch_id,
                "merchant_id": merchant_id,
                "source_row_id": record.row_index,
                "raw_values": record.raw_values,
                "canonical_values": record.canonical_values,
                "normalization_trace": [item.model_dump(mode="json") for item in record.traces],
                "validation_issues": record.validation_errors,
                "quality_components": {
                    key: value.model_dump(mode="json") for key, value in record.quality.components.items()
                },
                "automation_confidence": record.quality.overall,
                "automation_status": status,
                "review_status": REVIEW_NOT_REQUIRED if status == AUTOMATION_TRUSTED else REVIEW_PENDING,
                "duplicate": record.duplicate.model_dump(mode="json") if record.duplicate else None,
            }
        )
    return rows


def gold_rows(result: ProcessingResult, batch_id: int, merchant_id: int | None) -> list[dict[str, Any]]:
    rows = []
    for record in result.records:
        if automation_status(record) != AUTOMATION_TRUSTED:
            continue
        rows.append(
            {
                "batch_id": batch_id,
                "merchant_id": merchant_id,
                "source_row_id": record.row_index,
                **record.canonical_values,
                "automation_confidence": record.quality.overall,
                "automation_status": AUTOMATION_TRUSTED,
                "review_status": REVIEW_NOT_REQUIRED,
            }
        )
    return rows


def result_metrics(result: ProcessingResult) -> dict[str, Any]:
    statuses = [automation_status(record) for record in result.records]
    attention = sum(status != AUTOMATION_TRUSTED for status in statuses)
    drift_count, drift_severity = schema_drift_summary(result)
    return {
        "total_records": len(result.records),
        "auto_approved": statuses.count(AUTOMATION_TRUSTED),
        "needs_review": statuses.count(AUTOMATION_NEEDS_REVIEW),
        "invalid": statuses.count(AUTOMATION_INVALID),
        "duplicate_candidates": statuses.count(AUTOMATION_DUPLICATE),
        "attention_required": attention,
        "publishable": statuses.count(AUTOMATION_TRUSTED),
        "average_automation_confidence": round(
            sum(record.quality.overall for record in result.records) / max(1, len(result.records)) * 100,
            1,
        ),
        "schema_drift_count": drift_count,
        "schema_drift_severity": drift_severity,
        "columns": [
            {
                "source_name": profile.source_name,
                "null_percentage": profile.null_percentage,
                "validity_rate": profile.validity_rate,
            }
            for profile in result.profiles
        ],
    }
