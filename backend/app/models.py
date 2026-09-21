from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Merchant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    alias_config: str = "{}"
    created_at: datetime = Field(default_factory=utc_now)
    batches: list["UploadBatch"] = Relationship(back_populates="merchant")


class UploadBatch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: Optional[int] = Field(default=None, foreign_key="merchant.id", index=True)
    filename: str
    uploaded_at: datetime = Field(default_factory=utc_now)
    total_records: int = 0
    auto_approved_count: int = 0
    needs_review_count: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0
    attention_count: int = 0
    average_confidence: float = 0.0
    schema_drift_detected: bool = False
    default_currency: Optional[str] = None
    status: str = "completed"

    merchant: Optional[Merchant] = Relationship(back_populates="batches")
    records: list["CatalogRecord"] = Relationship(back_populates="batch")
    runs: list["ProcessingRun"] = Relationship(back_populates="batch")


class ProcessingRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="uploadbatch.id", index=True)
    processor_type: str = "local"
    status: str = "completed"
    started_at: datetime
    completed_at: Optional[datetime] = None
    config_snapshot: str = "{}"
    batch: Optional[UploadBatch] = Relationship(back_populates="runs")


class SchemaMapping(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="processingrun.id", index=True)
    source_field: str
    canonical_field: Optional[str] = None
    method: str
    confidence: float
    auto_applied: bool = False


class CatalogRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="uploadbatch.id", index=True)
    row_index: int
    raw_values: str = "{}"
    canonical_values: str = "{}"
    normalization_trace: str = "[]"
    quality_components: str = "{}"
    validation_errors: str = "[]"
    sku: Optional[str] = Field(default=None, index=True)
    original_product_name: Optional[str] = None
    original_category: Optional[str] = None
    original_price: Optional[str] = None
    original_inventory: Optional[str] = None
    original_tags: Optional[str] = None
    cleaned_product_name: Optional[str] = None
    cleaned_description: Optional[str] = None
    cleaned_category: Optional[str] = None
    cleaned_price: Optional[float] = None
    cleaned_currency: Optional[str] = None
    cleaned_inventory: Optional[int] = None
    cleaned_tags: Optional[str] = None
    automation_confidence: float = 0.0
    confidence_score: float = 0.0
    status: str = "Needs Review"
    recommended_action: str = "Review record"
    issue_reasons: str = "[]"
    severity: str = "Low"
    review_status: str = "pending"
    reviewed_at: Optional[datetime] = None
    reviewer_decision: Optional[str] = None
    corrected_values: str = "{}"
    reviewed: bool = False
    exportable: bool = False
    duplicate_of_record_id: Optional[int] = Field(default=None, foreign_key="catalogrecord.id")
    duplicate_method: Optional[str] = None
    duplicate_confidence: Optional[float] = None

    batch: Optional[UploadBatch] = Relationship(back_populates="records")
    review_items: list["ReviewItem"] = Relationship(back_populates="record")

    @property
    def upload_id(self) -> int:
        return self.batch_id


class ReviewItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: int = Field(foreign_key="catalogrecord.id", index=True)
    reason: str
    status: str = "pending"
    automated_confidence: float
    created_at: datetime = Field(default_factory=utc_now)
    reviewed_at: Optional[datetime] = None
    decision: Optional[str] = None
    corrected_values: str = "{}"
    record: Optional[CatalogRecord] = Relationship(back_populates="review_items")


class SchemaDriftReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="uploadbatch.id", index=True)
    profiles: str = "[]"
    missing_columns: str = "[]"
    unexpected_columns: str = "[]"
    suggested_mappings: str = "{}"
    auto_applied_mappings: str = "{}"
    unresolved_mappings: str = "{}"
    drift_severity: str = "Low"

    @property
    def upload_id(self) -> int:
        return self.batch_id


class Export(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: Optional[int] = Field(default=None, foreign_key="uploadbatch.id", index=True)
    export_type: str
    row_count: int
    created_at: datetime = Field(default_factory=utc_now)


CatalogUpload = UploadBatch
