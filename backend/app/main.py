from __future__ import annotations

import csv
import io
import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from .application import (
    OrchestrationError,
    load_batch_summary,
    orchestrate_catalog,
    processing_run_response,
    refresh_curated_artifact,
    refresh_processing_run,
)
from .database import create_db_and_tables, get_session
from .exports import export_catalog
from .ingestion import CatalogIngestionError
from .models import CatalogRecord, ReviewItem, SchemaDriftReport, SchemaMapping, ProcessingRun
from .processing import CatalogProcessor
from .policy import is_publishable, requires_attention
from .reviews import ReviewValidationError, apply_review_decision
from .runtime import build_processor, build_storage
from .scoping import latest_batch, resolve_batch_id
from .schemas import BatchSummary, ProcessingRunResponse, RecordResponse, ReviewDecisionRequest, ReviewItemResponse, ReviewRecordUpdate, SchemaDriftResponse, UploadSummary
from .serializers import record_response
from .storage import CatalogStorage


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="CatalogFlow", version="2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_processor() -> CatalogProcessor:
    return build_processor()


def get_storage() -> CatalogStorage:
    return build_storage()


def _resolve_batch_id(session: Session, batch_id: int | None) -> int | None:
    try:
        return resolve_batch_id(session, batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _process_upload(
    file: UploadFile,
    session: Session,
    processor: CatalogProcessor,
    storage: CatalogStorage,
    default_currency: str | None = None,
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")
    try:
        return orchestrate_catalog(
            file.filename,
            await file.read(),
            session,
            processor,
            storage,
            default_currency=default_currency,
        )
    except CatalogIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OrchestrationError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": str(exc), "batch_id": exc.batch_id, "run_id": exc.run_id, "error_code": exc.error_code},
        ) from exc


@app.post("/upload-catalog", response_model=UploadSummary)
async def upload_catalog(
    file: UploadFile = File(...),
    default_currency: str | None = Query(default=None, pattern="^[A-Za-z]{3}$"),
    session: Session = Depends(get_session),
    processor: CatalogProcessor = Depends(get_processor),
    storage: CatalogStorage = Depends(get_storage),
):
    return await _process_upload(file, session, processor, storage, default_currency)


@app.post("/batches", response_model=BatchSummary)
async def create_batch(
    file: UploadFile = File(...),
    default_currency: str | None = Query(default=None, pattern="^[A-Za-z]{3}$"),
    session: Session = Depends(get_session),
    processor: CatalogProcessor = Depends(get_processor),
    storage: CatalogStorage = Depends(get_storage),
):
    return await _process_upload(file, session, processor, storage, default_currency)


@app.get("/batches/{batch_id}", response_model=BatchSummary)
def get_batch(batch_id: int, session: Session = Depends(get_session)):
    summary = load_batch_summary(session, batch_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return summary


@app.get("/processing-runs/{run_id}", response_model=ProcessingRunResponse)
def get_processing_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(ProcessingRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Processing run not found.")
    return processing_run_response(run)


@app.post("/processing-runs/{run_id}/refresh", response_model=ProcessingRunResponse)
def refresh_run_status(
    run_id: int,
    session: Session = Depends(get_session),
    processor: CatalogProcessor = Depends(get_processor),
):
    try:
        return processing_run_response(refresh_processing_run(session, run_id, processor))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/latest-batch", response_model=BatchSummary)
def get_latest_batch(session: Session = Depends(get_session)):
    batch = latest_batch(session)
    if not batch:
        raise HTTPException(status_code=404, detail="No catalog batch is available.")
    return load_batch_summary(session, batch.id)


@app.get("/catalog", response_model=list[RecordResponse])
def get_catalog(batch_id: int | None = None, session: Session = Depends(get_session)):
    scoped_batch_id = _resolve_batch_id(session, batch_id)
    if scoped_batch_id is None:
        return []
    records = session.exec(
        select(CatalogRecord).where(CatalogRecord.batch_id == scoped_batch_id).order_by(CatalogRecord.id)
    ).all()
    return [record_response(record) for record in records if is_publishable(record)]


@app.get("/processed-records", response_model=list[RecordResponse])
@app.get("/batches/{batch_id}/records", response_model=list[RecordResponse])
def get_processed_records(batch_id: int | None = None, session: Session = Depends(get_session)):
    scoped_batch_id = _resolve_batch_id(session, batch_id)
    if scoped_batch_id is None:
        return []
    records = session.exec(
        select(CatalogRecord).where(CatalogRecord.batch_id == scoped_batch_id).order_by(CatalogRecord.id)
    ).all()
    return [record_response(record) for record in records]


@app.get("/review-queue", response_model=list[RecordResponse])
def get_review_queue(batch_id: int | None = None, session: Session = Depends(get_session)):
    scoped_batch_id = _resolve_batch_id(session, batch_id)
    if scoped_batch_id is None:
        return []
    records = session.exec(
        select(CatalogRecord).where(CatalogRecord.batch_id == scoped_batch_id).order_by(CatalogRecord.id)
    ).all()
    return [record_response(record) for record in records if requires_attention(record)]


@app.get("/batches/{batch_id}/review-items", response_model=list[ReviewItemResponse])
def get_batch_review_items(batch_id: int, session: Session = Depends(get_session)):
    _resolve_batch_id(session, batch_id)
    items = session.exec(
        select(ReviewItem).join(CatalogRecord).where(CatalogRecord.batch_id == batch_id).order_by(ReviewItem.id)
    ).all()
    return [
        {"id": item.id, "record_id": item.record_id, "batch_id": batch_id, "reason": item.reason,
         "status": item.status, "automated_confidence": item.automated_confidence, "created_at": item.created_at,
         "reviewed_at": item.reviewed_at, "decision": item.decision,
         "corrected_values": json.loads(item.corrected_values or "{}")}
        for item in items
    ]


@app.put("/review-queue/{record_id}", response_model=RecordResponse)
def update_review_record(
    record_id: int,
    payload: ReviewRecordUpdate,
    session: Session = Depends(get_session),
    storage: CatalogStorage = Depends(get_storage),
):
    record = session.get(CatalogRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    corrected = payload.model_dump(exclude={"mark_reviewed", "decision"}, exclude_none=True)
    try:
        reviewed = apply_review_decision(session, record, payload.decision, corrected)
    except ReviewValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "validation_errors": exc.errors,
            },
        ) from exc
    try:
        refresh_curated_artifact(session, storage, reviewed.batch_id)
    except OrchestrationError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc), "error_code": exc.error_code}) from exc
    return record_response(reviewed)


@app.post("/review-items/{review_item_id}/decision", response_model=RecordResponse)
def decide_review_item(
    review_item_id: int,
    payload: ReviewDecisionRequest,
    session: Session = Depends(get_session),
    storage: CatalogStorage = Depends(get_storage),
):
    item = session.get(ReviewItem, review_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found.")
    record = session.get(CatalogRecord, item.record_id)
    try:
        reviewed = apply_review_decision(
            session,
            record,
            payload.decision,
            payload.corrected_values.model_dump(exclude_none=True),
        )
    except ReviewValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "validation_errors": exc.errors,
            },
        ) from exc
    try:
        refresh_curated_artifact(session, storage, reviewed.batch_id)
    except OrchestrationError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc), "error_code": exc.error_code}) from exc
    return record_response(reviewed)


def _report_response(report: SchemaDriftReport) -> dict:
    return {
        "upload_id": report.batch_id, "batch_id": report.batch_id,
        "missing_columns": json.loads(report.missing_columns), "unexpected_columns": json.loads(report.unexpected_columns),
        "suggested_mappings": json.loads(report.suggested_mappings), "auto_applied_mappings": json.loads(report.auto_applied_mappings),
        "unresolved_mappings": json.loads(report.unresolved_mappings), "drift_severity": report.drift_severity,
        "profiles": json.loads(report.profiles),
    }


@app.get("/schema-drift-report", response_model=SchemaDriftResponse)
@app.get("/batches/{batch_id}/profiling", response_model=SchemaDriftResponse)
def get_schema_drift_report(batch_id: int | None = None, session: Session = Depends(get_session)):
    scoped_batch_id = _resolve_batch_id(session, batch_id)
    query = select(SchemaDriftReport)
    if scoped_batch_id is not None:
        query = query.where(SchemaDriftReport.batch_id == scoped_batch_id)
    report = session.exec(query.order_by(SchemaDriftReport.id.desc())).first()
    if not report:
        return {"upload_id": 0, "batch_id": 0, "missing_columns": [], "unexpected_columns": [],
                "suggested_mappings": {}, "auto_applied_mappings": {}, "unresolved_mappings": {},
                "drift_severity": "Low", "profiles": []}
    return _report_response(report)


@app.get("/batches/{batch_id}/mappings")
def get_mappings(batch_id: int, session: Session = Depends(get_session)):
    run = session.exec(select(ProcessingRun).where(ProcessingRun.batch_id == batch_id).order_by(ProcessingRun.id.desc())).first()
    if not run:
        raise HTTPException(status_code=404, detail="Batch not found.")
    mappings = session.exec(select(SchemaMapping).where(SchemaMapping.run_id == run.id)).all()
    return [{"source_field": item.source_field, "canonical_field": item.canonical_field, "method": item.method,
             "confidence": item.confidence, "auto_applied": item.auto_applied} for item in mappings]


@app.get("/export/cleaned-catalog")
def export_cleaned_catalog(batch_id: int | None = Query(default=None), session: Session = Depends(get_session)):
    return export_catalog(session, batch_id=batch_id)


@app.get("/export/review-report")
def export_review_report(batch_id: int | None = Query(default=None), session: Session = Depends(get_session)):
    return export_catalog(session, batch_id=batch_id, review_report=True)


@app.get("/export/schema-drift-report")
def export_schema_drift_report(batch_id: int | None = Query(default=None), session: Session = Depends(get_session)):
    scoped_batch_id = _resolve_batch_id(session, batch_id)
    query = select(SchemaDriftReport)
    if scoped_batch_id is not None:
        query = query.where(SchemaDriftReport.batch_id == scoped_batch_id)
    report = session.exec(query.order_by(SchemaDriftReport.id.desc())).first()
    if not report:
        raise HTTPException(status_code=404, detail="No schema drift report available.")
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["batch_id", "missing_columns", "unexpected_columns", "suggested_mappings", "auto_applied_mappings", "unresolved_mappings", "drift_severity"])
    writer.writerow([report.batch_id, report.missing_columns, report.unexpected_columns, report.suggested_mappings,
                     report.auto_applied_mappings, report.unresolved_mappings, report.drift_severity])
    stream.seek(0)
    return StreamingResponse(stream, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=schema-drift-report.csv"})
