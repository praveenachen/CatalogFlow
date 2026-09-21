from __future__ import annotations

from sqlmodel import Session, select

from .models import UploadBatch


def latest_batch(session: Session) -> UploadBatch | None:
    return session.exec(select(UploadBatch).order_by(UploadBatch.id.desc())).first()


def resolve_batch_id(session: Session, batch_id: int | None = None) -> int | None:
    if batch_id is not None:
        return batch_id
    batch = latest_batch(session)
    return batch.id if batch else None
