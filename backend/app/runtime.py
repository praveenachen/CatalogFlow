from __future__ import annotations

from .config import RuntimeSettings, load_runtime_settings
from .processing import CatalogProcessor, DatabricksCatalogProcessor, PandasCatalogProcessor
from .storage import CatalogStorage, LocalCatalogStorage, S3CatalogStorage, StorageConfigurationError


class RuntimeConfigurationError(ValueError):
    pass


def build_storage(settings: RuntimeSettings | None = None) -> CatalogStorage:
    settings = settings or load_runtime_settings()
    if settings.catalog_storage == "local":
        return LocalCatalogStorage(settings.local_storage_root)
    if settings.catalog_storage == "s3":
        if not settings.aws_s3_bucket:
            raise StorageConfigurationError("AWS_S3_BUCKET is required when CATALOG_STORAGE=s3.")
        return S3CatalogStorage(settings.aws_s3_bucket, settings.aws_region)
    raise RuntimeConfigurationError(f"Unsupported CATALOG_STORAGE: {settings.catalog_storage}")


def build_processor(settings: RuntimeSettings | None = None) -> CatalogProcessor:
    settings = settings or load_runtime_settings()
    if settings.catalog_processor == "local":
        return PandasCatalogProcessor()
    if settings.catalog_processor == "databricks":
        if settings.catalog_storage != "s3":
            raise RuntimeConfigurationError("Databricks processing requires CATALOG_STORAGE=s3; no silent local fallback is allowed.")
        if settings.databricks_job_id is None:
            raise RuntimeConfigurationError("DATABRICKS_JOB_ID is required when CATALOG_PROCESSOR=databricks.")
        return DatabricksCatalogProcessor(
            job_id=settings.databricks_job_id,
            host=settings.databricks_host,
            token=settings.databricks_token,
        )
    raise RuntimeConfigurationError(f"Unsupported CATALOG_PROCESSOR: {settings.catalog_processor}")
