"""Add cloud processing lifecycle and artifact metadata."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0003_cloud_processing"
down_revision = "0002_batch_attention_currency"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    upload_columns = _columns("uploadbatch")
    upload_additions = {
        "publishable_count": sa.Column("publishable_count", sa.Integer(), nullable=False, server_default="0"),
        "schema_drift_count": sa.Column("schema_drift_count", sa.Integer(), nullable=False, server_default="0"),
        "schema_drift_severity": sa.Column("schema_drift_severity", sa.String(), nullable=False, server_default="Low"),
        "quality_metrics": sa.Column("quality_metrics", sa.String(), nullable=False, server_default="{}"),
    }
    with op.batch_alter_table("uploadbatch") as batch:
        for name, column in upload_additions.items():
            if name not in upload_columns:
                batch.add_column(column)
    op.execute("UPDATE uploadbatch SET publishable_count = auto_approved_count")
    with op.batch_alter_table("uploadbatch") as batch:
        for name in upload_additions:
            batch.alter_column(name, server_default=None)

    run_columns = _columns("processingrun")
    run_additions = {
        "external_run_id": sa.Column("external_run_id", sa.String(), nullable=True),
        "error_code": sa.Column("error_code", sa.String(), nullable=True),
        "error_message": sa.Column("error_message", sa.String(), nullable=True),
        "raw_uri": sa.Column("raw_uri", sa.String(), nullable=True),
        "processed_uri": sa.Column("processed_uri", sa.String(), nullable=True),
        "curated_uri": sa.Column("curated_uri", sa.String(), nullable=True),
        "result_metadata": sa.Column("result_metadata", sa.String(), nullable=False, server_default="{}"),
    }
    with op.batch_alter_table("processingrun") as run:
        for name, column in run_additions.items():
            if name not in run_columns:
                run.add_column(column)
    if "ix_processingrun_external_run_id" not in _indexes("processingrun"):
        op.create_index("ix_processingrun_external_run_id", "processingrun", ["external_run_id"], unique=False)
    with op.batch_alter_table("processingrun") as run:
        run.alter_column("result_metadata", server_default=None)

    if "catalogartifact" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "catalogartifact",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("uploadbatch.id"), nullable=False),
            sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("merchant.id"), nullable=True),
            sa.Column("layer", sa.String(), nullable=False),
            sa.Column("object_uri", sa.String(), nullable=False),
            sa.Column("object_key", sa.String(), nullable=False),
            sa.Column("checksum", sa.String(), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    artifact_indexes = _indexes("catalogartifact")
    if "ix_catalogartifact_batch_id" not in artifact_indexes:
        op.create_index("ix_catalogartifact_batch_id", "catalogartifact", ["batch_id"])
    if "ix_catalogartifact_merchant_id" not in artifact_indexes:
        op.create_index("ix_catalogartifact_merchant_id", "catalogartifact", ["merchant_id"])


def downgrade() -> None:
    op.drop_index("ix_catalogartifact_merchant_id", table_name="catalogartifact")
    op.drop_index("ix_catalogartifact_batch_id", table_name="catalogartifact")
    op.drop_table("catalogartifact")
    with op.batch_alter_table("processingrun") as run:
        run.drop_index("ix_processingrun_external_run_id")
        for column in ("result_metadata", "curated_uri", "processed_uri", "raw_uri", "error_message", "error_code", "external_run_id"):
            run.drop_column(column)
    with op.batch_alter_table("uploadbatch") as batch:
        for column in ("quality_metrics", "schema_drift_severity", "schema_drift_count", "publishable_count"):
            batch.drop_column(column)
