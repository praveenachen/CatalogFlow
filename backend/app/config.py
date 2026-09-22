from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


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


@dataclass(frozen=True)
class RuntimeSettings:
    catalog_storage: str = "local"
    catalog_processor: str = "local"
    local_storage_root: Path = Path(".catalogflow-data")
    aws_region: str | None = None
    aws_s3_bucket: str | None = None
    databricks_host: str | None = None
    databricks_token: str | None = field(default=None, repr=False)
    databricks_job_id: int | None = None


def load_runtime_settings() -> RuntimeSettings:
    job_id = os.getenv("DATABRICKS_JOB_ID")
    return RuntimeSettings(
        catalog_storage=os.getenv("CATALOG_STORAGE", "local").strip().lower(),
        catalog_processor=os.getenv("CATALOG_PROCESSOR", "local").strip().lower(),
        local_storage_root=Path(os.getenv("LOCAL_CATALOG_STORAGE_ROOT", ".catalogflow-data")),
        aws_region=os.getenv("AWS_REGION"),
        aws_s3_bucket=os.getenv("AWS_S3_BUCKET"),
        databricks_host=os.getenv("DATABRICKS_HOST"),
        databricks_token=os.getenv("DATABRICKS_TOKEN"),
        databricks_job_id=int(job_id) if job_id else None,
    )
