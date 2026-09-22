from __future__ import annotations

import json

from .models import CatalogRecord
from .validation import validate_canonical_values


AUTOMATION_TRUSTED = "Auto-approved"
AUTOMATION_NEEDS_REVIEW = "Needs Review"
AUTOMATION_DUPLICATE = "Duplicate"
AUTOMATION_INVALID = "Invalid"

REVIEW_PENDING = "pending"
REVIEW_NOT_REQUIRED = "not_required"
REVIEW_APPROVED = "approved"
REVIEW_EDITED = "edited"
REVIEW_REJECTED = "rejected"

HUMAN_APPROVAL_STATES = {REVIEW_APPROVED, REVIEW_EDITED}


def _current_canonical_values(record: CatalogRecord) -> dict:
    tags = [item.strip() for item in (record.cleaned_tags or "").split(",") if item.strip()]
    return {
        "sku": record.sku,
        "product_name": record.cleaned_product_name,
        "description": record.cleaned_description,
        "category": record.cleaned_category,
        "price": record.cleaned_price,
        "currency": record.cleaned_currency,
        "inventory": record.cleaned_inventory,
        "tags": tags,
    }


def current_validation_errors(record: CatalogRecord) -> list[str]:
    """Validate the record as it exists now, including review corrections.

    Canonical Pydantic validation catches required/typed fields. Some ingestion
    rules intentionally add stricter errors (for example, a non-empty source
    inventory value that could not be parsed). Keep those errors active until
    the corresponding cleaned value is actually corrected.
    """
    errors = list(validate_canonical_values(_current_canonical_values(record)))
    try:
        original_errors = json.loads(record.validation_errors or "[]")
    except (TypeError, json.JSONDecodeError):
        original_errors = []

    if "inventory: invalid value" in original_errors and record.cleaned_inventory is None:
        errors.append("inventory: invalid value")

    return list(dict.fromkeys(errors))


def is_publishable(record: CatalogRecord) -> bool:
    """Single publish policy for automatic and human decisions.

    Human approval can resolve low-confidence or duplicate routing, but it may
    not override an actually invalid canonical record. Invalid values must be
    corrected first.
    """
    if record.review_status == REVIEW_REJECTED:
        return False
    if current_validation_errors(record):
        return False
    if record.review_status in HUMAN_APPROVAL_STATES:
        return True
    return record.status == AUTOMATION_TRUSTED and record.review_status == REVIEW_NOT_REQUIRED


def requires_attention(record: CatalogRecord) -> bool:
    if record.review_status == REVIEW_REJECTED:
        return False
    return not is_publishable(record)


def apply_publish_policy(record: CatalogRecord) -> bool:
    record.exportable = is_publishable(record)
    return record.exportable
