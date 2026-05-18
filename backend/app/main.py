from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
import io
import csv
import json

from .database import create_db_and_tables, get_session
from .models import CatalogUpload, CatalogRecord, SchemaDriftReport
from .schemas import UploadSummary, RecordResponse, SchemaDriftResponse, ReviewRecordUpdate
from .services import process_uploaded_catalog, normalize_review_record, export_csv_from_query, enrich_schema_report_response

app = FastAPI(title="CatalogFlow", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

@app.post("/upload-catalog", response_model=UploadSummary)
async def upload_catalog(file: UploadFile = File(...), session: Session = Depends(get_session)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")
    payload = await file.read()
    summary = process_uploaded_catalog(file.filename, payload, session)
    return summary

@app.get("/catalog", response_model=list[RecordResponse])
def get_catalog(session: Session = Depends(get_session)):
    records = session.exec(select(CatalogRecord).order_by(CatalogRecord.id)).all()
    def to_response(record: CatalogRecord) -> RecordResponse:
        return RecordResponse(
            id=record.id,
            original_product_name=record.original_product_name,
            original_category=record.original_category,
            original_price=record.original_price,
            original_inventory=record.original_inventory,
            original_tags=record.original_tags,
            cleaned_product_name=record.cleaned_product_name,
            cleaned_category=record.cleaned_category,
            cleaned_price=record.cleaned_price,
            cleaned_inventory=record.cleaned_inventory,
            cleaned_tags=record.cleaned_tags,
            confidence_score=record.confidence_score,
            status=record.status,
            recommended_action=record.recommended_action,
            issue_reasons=json.loads(record.issue_reasons or "[]"),
            severity=record.severity,
            reviewed=record.reviewed,
            exportable=record.exportable,
        )
    return [to_response(record) for record in records]

@app.get("/review-queue", response_model=list[RecordResponse])
def get_review_queue(session: Session = Depends(get_session)):
    records = session.exec(
        select(CatalogRecord).where(CatalogRecord.status != "Auto-approved").order_by(CatalogRecord.id)
    ).all()
    def to_response(record: CatalogRecord) -> RecordResponse:
        return RecordResponse(
            id=record.id,
            original_product_name=record.original_product_name,
            original_category=record.original_category,
            original_price=record.original_price,
            original_inventory=record.original_inventory,
            original_tags=record.original_tags,
            cleaned_product_name=record.cleaned_product_name,
            cleaned_category=record.cleaned_category,
            cleaned_price=record.cleaned_price,
            cleaned_inventory=record.cleaned_inventory,
            cleaned_tags=record.cleaned_tags,
            confidence_score=record.confidence_score,
            status=record.status,
            recommended_action=record.recommended_action,
            issue_reasons=json.loads(record.issue_reasons or "[]"),
            severity=record.severity,
            reviewed=record.reviewed,
            exportable=record.exportable,
        )
    return [to_response(record) for record in records]

@app.put("/review-queue/{record_id}", response_model=RecordResponse)
def update_review_record(record_id: int, payload: ReviewRecordUpdate, session: Session = Depends(get_session)):
    record = session.get(CatalogRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    normalize_review_record(record, payload)
    session.add(record)
    session.commit()
    session.refresh(record)
    return RecordResponse(
        id=record.id,
        original_product_name=record.original_product_name,
        original_category=record.original_category,
        original_price=record.original_price,
        original_inventory=record.original_inventory,
        original_tags=record.original_tags,
        cleaned_product_name=record.cleaned_product_name,
        cleaned_category=record.cleaned_category,
        cleaned_price=record.cleaned_price,
        cleaned_inventory=record.cleaned_inventory,
        cleaned_tags=record.cleaned_tags,
        confidence_score=record.confidence_score,
        status=record.status,
        recommended_action=record.recommended_action,
        issue_reasons=json.loads(record.issue_reasons or "[]"),
        severity=record.severity,
        reviewed=record.reviewed,
        exportable=record.exportable,
    )

@app.get("/schema-drift-report", response_model=SchemaDriftResponse)
def get_schema_drift_report(session: Session = Depends(get_session)):
    report = session.exec(select(SchemaDriftReport).order_by(SchemaDriftReport.id.desc())).first()
    if not report:
        return {
            "upload_id": 0,
            "missing_columns": [],
            "unexpected_columns": [],
            "suggested_mappings": {},
            "auto_applied_mappings": {},
            "unresolved_mappings": {},
            "drift_severity": "Low",
        }
    return enrich_schema_report_response(report)

@app.get("/export/cleaned-catalog")
def export_cleaned_catalog(session: Session = Depends(get_session)):
    query = select(CatalogRecord).where(CatalogRecord.exportable == True).order_by(CatalogRecord.id)
    return export_csv_from_query(session, query, include_review_columns=False)

@app.get("/export/review-report")
def export_review_report(session: Session = Depends(get_session)):
    query = select(CatalogRecord).where(CatalogRecord.status != "Auto-approved").order_by(CatalogRecord.id)
    return export_csv_from_query(session, query, include_review_columns=True)

@app.get("/export/schema-drift-report")
def export_schema_drift_report(session: Session = Depends(get_session)):
    report = session.exec(select(SchemaDriftReport).order_by(SchemaDriftReport.id.desc())).first()
    if not report:
        raise HTTPException(status_code=404, detail="No schema drift report available.")
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["missing_columns", "unexpected_columns", "suggested_mappings", "auto_applied_mappings", "unresolved_mappings", "drift_severity"])
    writer.writerow([
        report.missing_columns,
        report.unexpected_columns,
        report.suggested_mappings,
        report.auto_applied_mappings,
        report.unresolved_mappings,
        report.drift_severity,
    ])
    stream.seek(0)
    return StreamingResponse(stream, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=schema-drift-report.csv"})
