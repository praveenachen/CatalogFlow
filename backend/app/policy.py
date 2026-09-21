from __future__ import annotations

from .models import CatalogRecord


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


def is_publishable(record: CatalogRecord) -> bool:
    """The single publish policy for automatic and human decisions."""
    if record.review_status == REVIEW_REJECTED:
        return False
    if record.review_status in HUMAN_APPROVAL_STATES:
        return True
    return record.status == AUTOMATION_TRUSTED and record.review_status == REVIEW_NOT_REQUIRED


def requires_attention(record: CatalogRecord) -> bool:
    return record.review_status == REVIEW_PENDING


def apply_publish_policy(record: CatalogRecord) -> bool:
    record.exportable = is_publishable(record)
    return record.exportable
