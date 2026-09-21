from __future__ import annotations

import json

from .models import CatalogRecord
from .policy import is_publishable


def record_response(record: CatalogRecord) -> dict:
    return {
        "id": record.id, "batch_id": record.batch_id, "sku": record.sku,
        "original_product_name": record.original_product_name, "original_category": record.original_category,
        "original_price": record.original_price, "original_inventory": record.original_inventory,
        "original_tags": record.original_tags, "cleaned_product_name": record.cleaned_product_name,
        "cleaned_description": record.cleaned_description, "cleaned_category": record.cleaned_category,
        "cleaned_price": record.cleaned_price, "cleaned_currency": record.cleaned_currency,
        "cleaned_inventory": record.cleaned_inventory, "cleaned_tags": record.cleaned_tags,
        "confidence_score": record.confidence_score, "automation_confidence": record.automation_confidence,
        "quality_components": json.loads(record.quality_components or "{}"), "status": record.status,
        "normalization_trace": json.loads(record.normalization_trace or "[]"),
        "recommended_action": record.recommended_action, "issue_reasons": json.loads(record.issue_reasons or "[]"),
        "severity": record.severity, "review_status": record.review_status, "reviewed_at": record.reviewed_at,
        "reviewer_decision": record.reviewer_decision, "reviewed": record.reviewed, "exportable": is_publishable(record),
        "duplicate_of_record_id": record.duplicate_of_record_id, "duplicate_method": record.duplicate_method,
        "duplicate_confidence": record.duplicate_confidence,
    }
