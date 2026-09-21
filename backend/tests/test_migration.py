import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlmodel import SQLModel, create_engine

from app import models


def test_migration_preserves_legacy_phase_zero_data(tmp_path, monkeypatch):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE catalogupload (
            id INTEGER PRIMARY KEY, filename TEXT NOT NULL, uploaded_at DATETIME NOT NULL,
            total_records INTEGER NOT NULL, auto_approved_count INTEGER NOT NULL,
            needs_review_count INTEGER NOT NULL, duplicate_count INTEGER NOT NULL,
            invalid_count INTEGER NOT NULL, average_confidence FLOAT NOT NULL,
            schema_drift_detected BOOLEAN NOT NULL, schema_report_id INTEGER
        );
        CREATE TABLE catalogrecord (
            id INTEGER PRIMARY KEY, upload_id INTEGER, original_product_name TEXT,
            original_category TEXT, original_price TEXT, original_inventory TEXT, original_tags TEXT,
            cleaned_product_name TEXT, cleaned_category TEXT, cleaned_price FLOAT,
            cleaned_inventory INTEGER, cleaned_tags TEXT, confidence_score FLOAT NOT NULL,
            status TEXT NOT NULL, recommended_action TEXT NOT NULL, issue_reasons TEXT NOT NULL,
            severity TEXT NOT NULL, reviewed BOOLEAN NOT NULL, exportable BOOLEAN NOT NULL
        );
        CREATE TABLE schemadriftreport (
            id INTEGER PRIMARY KEY, upload_id INTEGER, missing_columns TEXT, unexpected_columns TEXT,
            suggested_mappings TEXT, auto_applied_mappings TEXT, unresolved_mappings TEXT,
            drift_severity TEXT NOT NULL
        );
        INSERT INTO catalogupload VALUES (1, 'legacy.csv', '2025-01-01', 1, 0, 1, 0, 0, 62.0, 1, 1);
        INSERT INTO catalogrecord VALUES (1, 1, 'raw shoe', 'shoes', '$10', '4 units', '#sale',
            'Raw Shoe', 'Footwear', 10.0, 4, 'sale', 62.0, 'Needs Review', 'Review record',
            '["Legacy uncertainty"]', 'Medium', 0, 0);
        INSERT INTO schemadriftreport VALUES (1, 1, '["currency"]', '["cost"]',
            '{"cost":"price"}', '{"cost":"price"}', '{}', 'Medium');
        """
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    backend = Path(__file__).parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    command.upgrade(config, "head")

    connection = sqlite3.connect(database)
    assert connection.execute("SELECT filename FROM uploadbatch WHERE id = 1").fetchone() == ("legacy.csv",)
    assert connection.execute(
        "SELECT attention_count, default_currency FROM uploadbatch WHERE id = 1"
    ).fetchone() == (1, None)
    migrated = connection.execute(
        "SELECT original_price, automation_confidence, review_status FROM catalogrecord WHERE id = 1"
    ).fetchone()
    assert migrated == ("$10", 0.62, "pending")
    assert connection.execute("SELECT automated_confidence FROM reviewitem").fetchone() == (0.62,)
    upload_columns = {row[1] for row in connection.execute("PRAGMA table_info(uploadbatch)")}
    assert {"publishable_count", "schema_drift_count", "schema_drift_severity", "quality_metrics"} <= upload_columns
    run_columns = {row[1] for row in connection.execute("PRAGMA table_info(processingrun)")}
    assert {"external_run_id", "error_code", "error_message", "raw_uri", "processed_uri", "curated_uri"} <= run_columns
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'catalogartifact'"
    ).fetchone() == ("catalogartifact",)
    connection.close()


def test_cloud_migration_resumes_when_create_all_precreated_artifact_table(tmp_path, monkeypatch):
    assert models.CatalogArtifact.__tablename__ == "catalogartifact"
    database = tmp_path / "precreated.db"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    backend = Path(__file__).parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))

    command.upgrade(config, "0002_batch_attention_currency")
    SQLModel.metadata.create_all(create_engine(database_url))
    command.upgrade(config, "head")

    connection = sqlite3.connect(database)
    assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0003_cloud_processing",)
    run_columns = {row[1] for row in connection.execute("PRAGMA table_info(processingrun)")}
    assert {"external_run_id", "result_metadata", "raw_uri", "processed_uri", "curated_uri"} <= run_columns
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'catalogartifact'"
    ).fetchone() == ("catalogartifact",)
    connection.close()
