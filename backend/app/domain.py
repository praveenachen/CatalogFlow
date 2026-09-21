from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MappingMethod(str, Enum):
    exact = "exact"
    alias = "alias"
    fuzzy = "fuzzy"
    unresolved = "unresolved"


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"


class CanonicalProduct(BaseModel):
    """Intentional API/domain contract; raw values live beside this model."""

    model_config = ConfigDict(str_strip_whitespace=True)

    sku: str | None = None
    product_name: str = Field(min_length=1)
    description: str | None = None
    category: str | None = None
    price: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    inventory: int | None = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("currency must be a three-letter alphabetic code")
        return value.upper()


class ColumnProfile(BaseModel):
    source_name: str
    inferred_type: str
    null_percentage: float
    unique_percentage: float
    sample_values: list[str]
    validity_rate: float | None = None


class MappingCandidate(BaseModel):
    source_field: str
    canonical_field: str | None
    confidence: float = Field(ge=0, le=1)
    method: MappingMethod
    auto_applied: bool = False


class NormalizationTrace(BaseModel):
    field: str
    original_value: Any = None
    normalized_value: Any = None
    rule: str
    certainty: float = Field(ge=0, le=1)


class QualityComponent(BaseModel):
    score: float = Field(ge=0, le=1)
    weight: float = Field(gt=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class QualityScore(BaseModel):
    overall: float = Field(ge=0, le=1)
    components: dict[str, QualityComponent]


class DuplicateCandidate(BaseModel):
    row_index: int
    matched_row_index: int
    method: str
    confidence: float = Field(ge=0, le=1)
    exact: bool


class ProcessedRecord(BaseModel):
    row_index: int
    raw_values: dict[str, Any]
    canonical_values: dict[str, Any]
    traces: list[NormalizationTrace]
    validation_errors: list[str]
    quality: QualityScore
    duplicate: DuplicateCandidate | None = None
    route: str


class ProcessingResult(BaseModel):
    profiles: list[ColumnProfile]
    mappings: list[MappingCandidate]
    records: list[ProcessedRecord]
    missing_columns: list[str]
    unexpected_columns: list[str]
    started_at: datetime
    completed_at: datetime
    default_currency: str | None = None
