from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from .models import CatalogRecord, ReviewItem, UploadBatch
from .normalization import normalize_category, normalize_tags
from .policy import REVIEW_REJECTED, apply_publish_policy, requires_attention


ALLOWED_CORRECTIONS = {"cleaned_category", "cleaned_price", "cleaned_inventory", "cleaned_tags"}


def apply_review_decision(
    session: Session,
    record: CatalogRecord,
    decision: str,
    corrected_values: dict[str, Any] | None = None,
) -> CatalogRecord:
    corrected = {key: value for key, value in (corrected_values or {}).items() if key in ALLOWED_CORRECTIONS and value is not None}
    if "cleaned_category" in corrected:
        corrected["cleaned_category"] = normalize_category(corrected["cleaned_category"])[0]
    if "cleaned_tags" in corrected:
        corrected["cleaned_tags"] = ", ".join(normalize_tags(corrected["cleaned_tags"])[0])
    for key, value in corrected.items():
        setattr(record, key, value)

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
    review_items = session.exec(select(ReviewItem).where(ReviewItem.record_id == record.id, ReviewItem.status == "pending")).all()
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
        session.add(batch)
    session.commit()
    session.refresh(record)
    return record
