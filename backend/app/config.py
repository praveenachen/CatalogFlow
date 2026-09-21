from __future__ import annotations

import os
from dataclasses import dataclass, field


CANONICAL_FIELDS = (
    "sku",
    "product_name",
    "description",
    "category",
    "price",
    "currency",
    "inventory",
    "tags",
)
REQUIRED_FIELDS = ("product_name", "price", "currency")


@dataclass(frozen=True)
class PipelineSettings:
    mapping_auto_apply_threshold: float = 0.90
    mapping_candidate_threshold: float = 0.72
    fuzzy_duplicate_threshold: float = 0.88
    publishable_score_threshold: float = 0.85
    quality_weights: dict[str, float] = field(
        default_factory=lambda: {
            "schema_mapping": 0.20,
            "required_completeness": 0.25,
            "value_validity": 0.25,
            "normalization_certainty": 0.15,
            "entity_certainty": 0.15,
        }
    )


SETTINGS = PipelineSettings()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./catalogflow.db")
