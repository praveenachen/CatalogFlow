from __future__ import annotations

import csv
import io

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from .models import CatalogRecord, Export
from .policy import is_publishable
from .scoping import resolve_batch_id


def export_catalog(session: Session, batch_id: int | None = None, review_report: bool = False) -> StreamingResponse:
    scoped_batch_id = resolve_batch_id(session, batch_id)
    if scoped_batch_id is None:
        raise HTTPException(status_code=404, detail="No catalog batch is available for export.")
    candidates = session.exec(
        select(CatalogRecord).where(CatalogRecord.batch_id == scoped_batch_id).order_by(CatalogRecord.id)
    ).all()
    records = (
        [record for record in candidates if not is_publishable(record)]
        if review_report
        else [record for record in candidates if is_publishable(record)]
    )
    if not records:
        export_name = "review records" if review_report else "publishable records"
        raise HTTPException(status_code=404, detail=f"This batch has no {export_name} to export.")
    stream = io.StringIO()
    writer = csv.writer(stream)
    headers = ["sku", "product_name", "description", "category", "price", "currency", "inventory", "tags"]
    if review_report:
        headers.extend(["automation_confidence", "review_status", "issue_reasons", "severity", "reviewer_decision"])
    writer.writerow(headers)
    for record in records:
        row = [record.sku, record.cleaned_product_name, record.cleaned_description, record.cleaned_category, record.cleaned_price,
               record.cleaned_currency, record.cleaned_inventory, record.cleaned_tags]
        if review_report:
            row.extend([record.automation_confidence, record.review_status, record.issue_reasons, record.severity, record.reviewer_decision])
        writer.writerow(row)
    session.add(Export(batch_id=scoped_batch_id, export_type="review" if review_report else "publishable", row_count=len(records)))
    session.commit()
    stream.seek(0)
    filename = "review-report.csv" if review_report else "cleaned-catalog.csv"
    return StreamingResponse(stream, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
