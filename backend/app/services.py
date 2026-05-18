from __future__ import annotations
import csv
import io
import json
from datetime import datetime
from typing import Any
import pandas as pd
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from .models import CatalogUpload, CatalogRecord, SchemaDriftReport

EXPECTED_SCHEMA = ["product_name", "category", "price", "inventory", "tags", "description"]
COLUMN_SUGGESTIONS = {
    "item_name": "product_name",
    "title": "product_name",
    "cost": "price",
    "retail_price": "price",
    "stock": "inventory",
    "inventory_count": "inventory",
    "product_type": "category",
    "labels": "tags",
    "sku": "product_name",
}
CATEGORY_NORMALIZATION = {
    "womens shoes": "Footwear",
    "women footwear": "Footwear",
    "ladies shoes": "Footwear",
    "mens tops": "Apparel",
    "shirts": "Apparel",
    "t-shirt": "Apparel",
    "tee": "Apparel",
    "skincare": "Beauty",
    "beauty": "Beauty",
    "cosmetics": "Beauty",
    "laptop accessories": "Electronics",
    "electronics": "Electronics",
    "tech": "Electronics",
    "home goods": "Home",
    "decor": "Home",
    "furniture": "Home",
}
STANDARD_CATEGORIES = ["Apparel", "Beauty", "Electronics", "Footwear", "Home", "Accessories", "Outdoors"]

STATUS_AUTO = "Auto-approved"
STATUS_REVIEW = "Needs Review"
STATUS_DUPLICATE = "Duplicate"
STATUS_INVALID = "Invalid"

SEVERITY_DELTA = {"Low": 0, "Medium": 1, "High": 2}


def safe_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def title_case_name(value: str) -> str:
    return " ".join(word.capitalize() for word in value.split()) if value else ""


def clean_price(value: Any) -> tuple[float | None, bool]:
    raw = safe_string(value)
    if not raw:
        return None, False
    raw = raw.replace("$", "").replace(",", "").strip()
    try:
        return float(raw), True
    except ValueError:
        return None, False


def clean_inventory(value: Any) -> tuple[int | None, bool]:
    raw = safe_string(value)
    if not raw:
        return None, False
    raw = raw.replace("pcs", "").replace("units", "").replace("-", "").strip()
    if raw.isdigit():
        return int(raw), True
    try:
        return int(float(raw)), True
    except ValueError:
        return None, False


def normalize_tags(value: Any) -> str:
    raw = safe_string(value)
    if not raw:
        return ""
    tags = [tag.strip().lower().replace("#", "") for tag in raw.replace("|", ",").split(",") if tag.strip()]
    return ", ".join(sorted(set(tags)))


def normalize_category(value: Any) -> tuple[str, bool]:
    raw = safe_string(value).lower()
    if not raw:
        return "", False
    normalized = CATEGORY_NORMALIZATION.get(raw)
    if normalized:
        return normalized, True
    for keyword, target in CATEGORY_NORMALIZATION.items():
        if keyword in raw:
            return target, True
    candidate = raw.title()
    return candidate, False


def detect_schema_drift(df: pd.DataFrame) -> dict[str, Any]:
    uploaded_columns = [col.strip() for col in df.columns]
    missing = [col for col in EXPECTED_SCHEMA if col not in uploaded_columns]
    unexpected = [col for col in uploaded_columns if col not in EXPECTED_SCHEMA]
    suggested = {}
    auto_applied = {}
    unresolved = {}
    for col in unexpected:
        key = col.strip().lower()
        if key in COLUMN_SUGGESTIONS:
            suggested[col] = COLUMN_SUGGESTIONS[key]
            auto_applied[col] = COLUMN_SUGGESTIONS[key]
        else:
            unresolved[col] = "unknown"
    drift_score = len(missing) * 2 + len(unexpected) + len(unresolved) * 2
    drift_severity = "High" if drift_score >= 4 else "Medium" if drift_score >= 2 else "Low"
    return {
        "missing_columns": missing,
        "unexpected_columns": unexpected,
        "suggested_mappings": suggested,
        "auto_applied_mappings": auto_applied,
        "unresolved_mappings": unresolved,
        "drift_severity": drift_severity,
    }


def apply_schema_mappings(df: pd.DataFrame, drift: dict[str, Any]) -> pd.DataFrame:
    rename_map = {col: target for col, target in drift["auto_applied_mappings"].items()}
    return df.rename(columns=rename_map)


def build_catalog_record(row: pd.Series, drift: dict[str, Any], row_index: int) -> dict[str, Any]:
    original = {
        "product_name": safe_string(row.get("product_name", "")),
        "category": safe_string(row.get("category", "")),
        "price": safe_string(row.get("price", "")),
        "inventory": safe_string(row.get("inventory", "")),
        "tags": safe_string(row.get("tags", "")),
    }
    cleaned_name = title_case_name(original["product_name"])
    cleaned_category, category_inferred = normalize_category(original["category"])
    cleaned_price, price_valid = clean_price(original["price"])
    cleaned_inventory, inventory_valid = clean_inventory(original["inventory"])
    cleaned_tags = normalize_tags(original["tags"])
    issue_reasons = []
    severity = "Low"
    score = 100

    if not cleaned_name:
        issue_reasons.append("Missing product name")
        score -= 30
        severity = "High"
    if cleaned_price is None:
        issue_reasons.append("Invalid or missing price")
        score -= 25
        severity = "High"
    if cleaned_inventory is None:
        issue_reasons.append("Invalid or missing inventory")
        score -= 20
        if severity != "High":
            severity = "Medium"
    if cleaned_category and not category_inferred:
        issue_reasons.append("Category requires normalization")
        score -= 5
    if cleaned_category and category_inferred:
        issue_reasons.append("Category mapped from fuzzy input")
        score -= 10
        if severity == "Low":
            severity = "Medium"
    if drift["missing_columns"] or drift["unexpected_columns"]:
        issue_reasons.append("Upload schema drift detected")
        score -= 10
        if severity == "Low":
            severity = "Medium"
    if not original["category"]:
        issue_reasons.append("Missing category")
        score -= 10
        if severity == "Low":
            severity = "Medium"

    score = max(0, min(100, score))
    status = STATUS_AUTO if score >= 85 and severity == "Low" else STATUS_INVALID if score < 50 else STATUS_DUPLICATE if False else STATUS_REVIEW
    recommended_action = "Auto-approve" if status == STATUS_AUTO else "Block from export" if status == STATUS_INVALID else "Review record"
    exportable = status in {STATUS_AUTO, STATUS_REVIEW}
    return {
        "original_product_name": original["product_name"],
        "original_category": original["category"],
        "original_price": original["price"],
        "original_inventory": original["inventory"],
        "original_tags": original["tags"],
        "cleaned_product_name": cleaned_name,
        "cleaned_category": cleaned_category or "",
        "cleaned_price": cleaned_price,
        "cleaned_inventory": cleaned_inventory,
        "cleaned_tags": cleaned_tags,
        "confidence_score": float(score),
        "status": status,
        "recommended_action": recommended_action,
        "issue_reasons": issue_reasons,
        "severity": severity,
        "reviewed": False,
        "exportable": exportable,
    }


def detect_duplicates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], int] = {}
    for record in records:
        key = (record["cleaned_product_name"].lower(), record["cleaned_category"].lower())
        if key[0] and key[1] and key in seen:
            record["status"] = STATUS_DUPLICATE
            record["recommended_action"] = "Check duplicate"
            record["issue_reasons"].append("Duplicate product detected")
            record["severity"] = "Medium"
            record["exportable"] = False
        else:
            seen[key] = 1
    return records


def evaluate_exportable(record: dict[str, Any]) -> bool:
    return record["status"] in {STATUS_AUTO, STATUS_REVIEW}


def process_uploaded_catalog(filename: str, payload: bytes, session: Session) -> dict[str, Any]:
    df = pd.read_csv(io.BytesIO(payload))
    drift = detect_schema_drift(df)
    df = apply_schema_mappings(df, drift)
    for col in EXPECTED_SCHEMA:
        if col not in df.columns:
            df[col] = ""
    records = []
    for idx, row in df.iterrows():
        record = build_catalog_record(row, drift, idx)
        records.append(record)
    records = detect_duplicates(records)
    upload = CatalogUpload(
        filename=filename,
        total_records=len(records),
        auto_approved_count=sum(1 for record in records if record["status"] == STATUS_AUTO),
        needs_review_count=sum(1 for record in records if record["status"] == STATUS_REVIEW),
        duplicate_count=sum(1 for record in records if record["status"] == STATUS_DUPLICATE),
        invalid_count=sum(1 for record in records if record["status"] == STATUS_INVALID),
        average_confidence=round(sum(record["confidence_score"] for record in records) / max(1, len(records)), 1),
        schema_drift_detected=bool(drift["missing_columns"] or drift["unexpected_columns"]),
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    report = SchemaDriftReport(
        upload_id=upload.id,
        missing_columns=json.dumps(drift["missing_columns"]),
        unexpected_columns=json.dumps(drift["unexpected_columns"]),
        suggested_mappings=json.dumps(drift["suggested_mappings"]),
        auto_applied_mappings=json.dumps(drift["auto_applied_mappings"]),
        unresolved_mappings=json.dumps(drift["unresolved_mappings"]),
        drift_severity=drift["drift_severity"],
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    upload.schema_report_id = report.id
    session.add(upload)
    for record_data in records:
        catalog_record = CatalogRecord(
            upload_id=upload.id,
            original_product_name=record_data["original_product_name"],
            original_category=record_data["original_category"],
            original_price=record_data["original_price"],
            original_inventory=record_data["original_inventory"],
            original_tags=record_data["original_tags"],
            cleaned_product_name=record_data["cleaned_product_name"],
            cleaned_category=record_data["cleaned_category"],
            cleaned_price=record_data["cleaned_price"],
            cleaned_inventory=record_data["cleaned_inventory"],
            cleaned_tags=record_data["cleaned_tags"],
            confidence_score=record_data["confidence_score"],
            status=record_data["status"],
            recommended_action=record_data["recommended_action"],
            issue_reasons=json.dumps(record_data["issue_reasons"]),
            severity=record_data["severity"],
            reviewed=record_data["reviewed"],
            exportable=evaluate_exportable(record_data),
        )
        session.add(catalog_record)
    session.commit()
    return {
        "upload_id": upload.id,
        "filename": upload.filename,
        "total_records": upload.total_records,
        "auto_approved_count": upload.auto_approved_count,
        "needs_review_count": upload.needs_review_count,
        "duplicate_count": upload.duplicate_count,
        "invalid_count": upload.invalid_count,
        "average_confidence": upload.average_confidence,
        "schema_drift_detected": upload.schema_drift_detected,
        "schema_report": {
            "missing_columns": drift["missing_columns"],
            "unexpected_columns": drift["unexpected_columns"],
            "suggested_mappings": drift["suggested_mappings"],
            "auto_applied_mappings": drift["auto_applied_mappings"],
            "unresolved_mappings": drift["unresolved_mappings"],
            "drift_severity": drift["drift_severity"],
        },
    }


def normalize_review_record(record: CatalogRecord, payload: Any) -> None:
    if payload.cleaned_category is not None:
        normalized, _ = normalize_category(payload.cleaned_category)
        record.cleaned_category = normalized or payload.cleaned_category
    if payload.cleaned_price is not None:
        record.cleaned_price = payload.cleaned_price
    if payload.cleaned_inventory is not None:
        record.cleaned_inventory = payload.cleaned_inventory
    if payload.cleaned_tags is not None:
        record.cleaned_tags = normalize_tags(payload.cleaned_tags)
    if payload.mark_reviewed:
        record.reviewed = True
    record.issue_reasons = json.dumps([])
    record.confidence_score = 100.0
    if not record.cleaned_product_name:
        record.confidence_score -= 30
    if not record.cleaned_category:
        record.confidence_score -= 10
    if record.cleaned_price is None:
        record.confidence_score -= 25
    if record.cleaned_inventory is None:
        record.confidence_score -= 20
    if not record.cleaned_tags:
        record.confidence_score -= 5
    if record.confidence_score < 50:
        record.status = STATUS_INVALID
        record.recommended_action = "Block from export"
        record.severity = "High"
    elif record.confidence_score >= 85:
        record.status = STATUS_AUTO
        record.recommended_action = "Auto-approve"
        record.severity = "Low"
    else:
        record.status = STATUS_REVIEW
        record.recommended_action = "Review record"
        record.severity = "Medium"
    record.exportable = record.status in {STATUS_AUTO, STATUS_REVIEW}


def export_csv_from_query(session: Session, query: Any, include_review_columns: bool = False):
    records = session.exec(query).all()
    stream = io.StringIO()
    writer = csv.writer(stream)
    headers = ["product_name", "category", "price", "inventory", "tags", "confidence_score", "status", "recommended_action"]
    if include_review_columns:
        headers.extend(["issue_reasons", "severity", "reviewed"])
    writer.writerow(headers)
    for record in records:
        row = [
            record.cleaned_product_name,
            record.cleaned_category,
            record.cleaned_price,
            record.cleaned_inventory,
            record.cleaned_tags,
            record.confidence_score,
            record.status,
            record.recommended_action,
        ]
        if include_review_columns:
            row.extend([record.issue_reasons, record.severity, record.reviewed])
        writer.writerow(row)
    stream.seek(0)
    filename = "cleaned-catalog.csv" if not include_review_columns else "review-report.csv"
    return StreamingResponse(stream, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


def enrich_schema_report_response(report: SchemaDriftReport) -> dict[str, Any]:
    return {
        "upload_id": report.upload_id,
        "missing_columns": json.loads(report.missing_columns or "[]"),
        "unexpected_columns": json.loads(report.unexpected_columns or "[]"),
        "suggested_mappings": json.loads(report.suggested_mappings or "{}"),
        "auto_applied_mappings": json.loads(report.auto_applied_mappings or "{}"),
        "unresolved_mappings": json.loads(report.unresolved_mappings or "{}"),
        "drift_severity": report.drift_severity,
    }
