from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class UploadSummary(BaseModel):
    upload_id: int
    filename: str
    total_records: int
    auto_approved_count: int
    needs_review_count: int
    duplicate_count: int
    invalid_count: int
    average_confidence: float
    schema_drift_detected: bool
    schema_report: Dict[str, Any]

class RecordResponse(BaseModel):
    id: int
    original_product_name: Optional[str]
    original_category: Optional[str]
    original_price: Optional[str]
    original_inventory: Optional[str]
    original_tags: Optional[str]
    cleaned_product_name: Optional[str]
    cleaned_category: Optional[str]
    cleaned_price: Optional[float]
    cleaned_inventory: Optional[int]
    cleaned_tags: Optional[str]
    confidence_score: float
    status: str
    recommended_action: str
    issue_reasons: List[str]
    severity: str
    reviewed: bool
    exportable: bool

class SchemaDriftResponse(BaseModel):
    upload_id: int
    missing_columns: List[str]
    unexpected_columns: List[str]
    suggested_mappings: Dict[str, str]
    auto_applied_mappings: Dict[str, str]
    unresolved_mappings: Dict[str, str]
    drift_severity: str

class ReviewRecordUpdate(BaseModel):
    cleaned_category: Optional[str]
    cleaned_price: Optional[float]
    cleaned_inventory: Optional[int]
    cleaned_tags: Optional[str]
    mark_reviewed: Optional[bool] = True
