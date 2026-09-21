from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .domain import ColumnProfile, MappingCandidate, QualityComponent


class SchemaReport(BaseModel):
    missing_columns: list[str]
    unexpected_columns: list[str]
    suggested_mappings: dict[str, str]
    auto_applied_mappings: dict[str, str]
    unresolved_mappings: dict[str, str]
    drift_severity: str
    profiles: list[ColumnProfile] = Field(default_factory=list)


class UploadSummary(BaseModel):
    upload_id: int
    batch_id: int
    filename: str
    total_records: int
    auto_approved_count: int
    needs_review_count: int
    duplicate_count: int
    invalid_count: int
    attention_count: int
    average_confidence: float
    schema_drift_detected: bool
    default_currency: str | None = None
    schema_report: SchemaReport


class BatchSummary(UploadSummary):
    status: str
    mappings: list[MappingCandidate] = Field(default_factory=list)


class RecordResponse(BaseModel):
    id: int
    batch_id: int
    sku: str | None = None
    original_product_name: str | None = None
    original_category: str | None = None
    original_price: str | None = None
    original_inventory: str | None = None
    original_tags: str | None = None
    cleaned_product_name: str | None = None
    cleaned_description: str | None = None
    cleaned_category: str | None = None
    cleaned_price: float | None = None
    cleaned_currency: str | None = None
    cleaned_inventory: int | None = None
    cleaned_tags: str | None = None
    confidence_score: float
    automation_confidence: float
    quality_components: dict[str, QualityComponent]
    normalization_trace: list[dict[str, Any]]
    status: str
    recommended_action: str
    issue_reasons: list[str]
    severity: str
    review_status: str
    reviewed_at: datetime | None = None
    reviewer_decision: str | None = None
    reviewed: bool
    exportable: bool
    duplicate_of_record_id: int | None = None
    duplicate_method: str | None = None
    duplicate_confidence: float | None = None


class SchemaDriftResponse(SchemaReport):
    upload_id: int
    batch_id: int


class ReviewRecordUpdate(BaseModel):
    cleaned_category: str | None = None
    cleaned_price: float | None = Field(default=None, ge=0)
    cleaned_inventory: int | None = Field(default=None, ge=0)
    cleaned_tags: str | None = None
    mark_reviewed: bool = True
    decision: Literal["approved", "edited", "rejected"] = "edited"


class ReviewCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cleaned_category: str | None = None
    cleaned_price: float | None = Field(default=None, ge=0)
    cleaned_inventory: int | None = Field(default=None, ge=0)
    cleaned_tags: str | None = None


class ReviewDecisionRequest(BaseModel):
    decision: Literal["approved", "edited", "rejected"]
    corrected_values: ReviewCorrections = Field(default_factory=ReviewCorrections)


class ReviewItemResponse(BaseModel):
    id: int
    record_id: int
    batch_id: int
    reason: str
    status: str
    automated_confidence: float
    created_at: datetime
    reviewed_at: datetime | None = None
    decision: str | None = None
    corrected_values: dict[str, Any]
