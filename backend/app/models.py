from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class CatalogUpload(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    total_records: int = 0
    auto_approved_count: int = 0
    needs_review_count: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0
    average_confidence: float = 0.0
    schema_drift_detected: bool = False
    schema_report_id: Optional[int] = Field(default=None, foreign_key="schemadriftreport.id")

    records: list["CatalogRecord"] = Relationship(back_populates="upload")

class CatalogRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    upload_id: Optional[int] = Field(default=None, foreign_key="catalogupload.id")
    original_product_name: Optional[str] = None
    original_category: Optional[str] = None
    original_price: Optional[str] = None
    original_inventory: Optional[str] = None
    original_tags: Optional[str] = None
    cleaned_product_name: Optional[str] = None
    cleaned_category: Optional[str] = None
    cleaned_price: Optional[float] = None
    cleaned_inventory: Optional[int] = None
    cleaned_tags: Optional[str] = None
    confidence_score: float = 0.0
    status: str = "Needs Review"
    recommended_action: str = "Review record"
    issue_reasons: str = Field(default="[]")
    severity: str = "Low"
    reviewed: bool = False
    exportable: bool = False

    upload: Optional[CatalogUpload] = Relationship(back_populates="records")

class SchemaDriftReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    upload_id: Optional[int] = Field(default=None, foreign_key="catalogupload.id")
    missing_columns: Optional[str] = Field(default="[]")
    unexpected_columns: Optional[str] = Field(default="[]")
    suggested_mappings: Optional[str] = Field(default="{}")
    auto_applied_mappings: Optional[str] = Field(default="{}")
    unresolved_mappings: Optional[str] = Field(default="{}")
    drift_severity: str = "Low"
