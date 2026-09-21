from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from .models import CatalogRecord, ReviewItem, UploadBatch
from .normalization import normalize_category, normalize_tags
from .policy import (
    HUMAN_APPROVAL_STATES,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    apply_publish_policy,
    current_validation_errors,
    is_publishable,
    requires_attention,
)


ALLOWED_CORRECTIONS = {
    "cleaned_product_name",
    "cleaned_description",
    "cleaned_category",
    "cleaned_price",
    "cleaned_currency",
    "cleaned_inventory",
    "cleaned_tags",
}


class ReviewValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Record still has validation errors and cannot be approved for publication.")


def apply_review_decision(
    session: Session,
    record: CatalogRecord,
    decision: str,
    corrected_values: dict[str, Any] | None = None,
) -> CatalogRecord:
    corrected = {
        key: value
        for key, value in (corrected_values or {}).items()
        if key in ALLOWED_CORRECTIONS and value is not None
    }
    if "cleaned_product_name" in corrected:
        corrected["cleaned_product_name"] = str(corrected["cleaned_product_name"]).strip()
    if "cleaned_description" in corrected:
        corrected["cleaned_description"] = str(corrected["cleaned_description"]).strip()
    if "cleaned_category" in corrected:
        corrected["cleaned_category"] = normalize_category(corrected["cleaned_category"])[0]
    if "cleaned_currency" in corrected:
        corrected["cleaned_currency"] = str(corrected["cleaned_currency"]).strip().upper()
    if "cleaned_tags" in corrected:
        corrected["cleaned_tags"] = ", ".join(normalize_tags(corrected["cleaned_tags"])[0])

    for key, value in corrected.items():
        setattr(record, key, value)

    # Human review can resolve ambiguity, but it cannot waive an invalid data
    # contract. Require the corrected record to be valid before final approval.
    if decision in HUMAN_APPROVAL_STATES:
        remaining_errors = current_validation_errors(record)
        if remaining_errors:
            session.rollback()
            raise ReviewValidationError(remaining_errors)

    now = datetime.now(timezone.utc)
    record.reviewed = True
    record.reviewed_at = now
    record.review_status = decision
    record.reviewer_decision = decision
    record.corrected_values = json.dumps(corrected, sort_keys=True)
    if decision == REVIEW_REJECTED:
        record.recommended_action = "Do not publish"
    else:
        record.recommended_action = "Publish with review history"
    apply_publish_policy(record)

    review_items = session.exec(
        select(ReviewItem).where(ReviewItem.record_id == record.id, ReviewItem.status == REVIEW_PENDING)
    ).all()
    for item in review_items:
        item.status, item.reviewed_at, item.decision = decision, now, decision
        item.corrected_values = record.corrected_values
        session.add(item)

    session.add(record)
    session.flush()
    batch = session.get(UploadBatch, record.batch_id)
    if batch:
        records = session.exec(select(CatalogRecord).where(CatalogRecord.batch_id == record.batch_id)).all()
        batch.attention_count = sum(requires_attention(item) for item in records)
        batch.publishable_count = sum(is_publishable(item) for item in records)
        session.add(batch)
    session.commit()
    session.refresh(record)
    return record
