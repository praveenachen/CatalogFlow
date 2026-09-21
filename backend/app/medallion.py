from __future__ import annotations

import json
from typing import Any, Iterable

from .models import CatalogRecord, UploadBatch
from .policy import is_publishable


CANONICAL_EXPORT_FIELDS = ("sku", "product_name", "description", "category", "price", "currency", "inventory", "tags")


def _line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def silver_payload(records: Iterable[CatalogRecord]) -> bytes:
    lines = []
    for record in records:
        lines.append(
            _line(
                {
                    "record_id": record.id,
                    "batch_id": record.batch_id,
                    "source_row_id": record.row_index,
                    "raw_values": json.loads(record.raw_values or "{}"),
                    "canonical_values": json.loads(record.canonical_values or "{}"),
                    "normalization_trace": json.loads(record.normalization_trace or "[]"),
                    "validation_issues": json.loads(record.validation_errors or "[]"),
                    "quality_components": json.loads(record.quality_components or "{}"),
                    "automation_confidence": record.automation_confidence,
                    "automation_status": record.status,
                    "review_status": record.review_status,
                    "duplicate_of_record_id": record.duplicate_of_record_id,
                    "duplicate_method": record.duplicate_method,
                    "duplicate_confidence": record.duplicate_confidence,
                }
            )
        )
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def gold_payload(records: Iterable[CatalogRecord]) -> bytes:
    lines = []
    for record in records:
        if not is_publishable(record):
            continue
        lines.append(
            _line(
                {
                    "sku": record.sku,
                    "product_name": record.cleaned_product_name,
                    "description": record.cleaned_description,
                    "category": record.cleaned_category,
                    "price": record.cleaned_price,
                    "currency": record.cleaned_currency,
                    "inventory": record.cleaned_inventory,
                    "tags": record.cleaned_tags,
                    "automation_confidence": record.automation_confidence,
                    "automation_status": record.status,
                    "review_status": record.review_status,
                    "corrected_values": json.loads(record.corrected_values or "{}"),
                }
            )
        )
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def quality_metrics(batch: UploadBatch, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_records": batch.total_records,
        "auto_approved": batch.auto_approved_count,
        "needs_review": batch.needs_review_count,
        "invalid": batch.invalid_count,
        "duplicate_candidates": batch.duplicate_count,
        "attention_required": batch.attention_count,
        "publishable": batch.publishable_count,
        "average_automation_confidence": batch.average_confidence,
        "schema_drift_count": batch.schema_drift_count,
        "schema_drift_severity": batch.schema_drift_severity,
        "columns": [
            {
                "source_name": profile["source_name"],
                "null_percentage": profile["null_percentage"],
                "validity_rate": profile.get("validity_rate"),
            }
            for profile in profiles
        ],
    }
