"""Phase 1 ETL core domain schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0001_phase1_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    legacy = "catalogupload" in tables
    if legacy:
        op.rename_table("catalogupload", "legacy_catalogupload")
        op.rename_table("catalogrecord", "legacy_catalogrecord")
        op.rename_table("schemadriftreport", "legacy_schemadriftreport")
    op.create_table("merchant", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(), nullable=False), sa.Column("alias_config", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_merchant_name", "merchant", ["name"], unique=True)
    op.create_table("uploadbatch", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("merchant.id")), sa.Column("filename", sa.String(), nullable=False), sa.Column("uploaded_at", sa.DateTime(), nullable=False), sa.Column("total_records", sa.Integer(), nullable=False), sa.Column("auto_approved_count", sa.Integer(), nullable=False), sa.Column("needs_review_count", sa.Integer(), nullable=False), sa.Column("duplicate_count", sa.Integer(), nullable=False), sa.Column("invalid_count", sa.Integer(), nullable=False), sa.Column("average_confidence", sa.Float(), nullable=False), sa.Column("schema_drift_detected", sa.Boolean(), nullable=False), sa.Column("status", sa.String(), nullable=False))
    op.create_index("ix_uploadbatch_merchant_id", "uploadbatch", ["merchant_id"])
    op.create_table("processingrun", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("uploadbatch.id"), nullable=False), sa.Column("processor_type", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("started_at", sa.DateTime(), nullable=False), sa.Column("completed_at", sa.DateTime()), sa.Column("config_snapshot", sa.String(), nullable=False))
    op.create_index("ix_processingrun_batch_id", "processingrun", ["batch_id"])
    op.create_table("schemamapping", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("processingrun.id"), nullable=False), sa.Column("source_field", sa.String(), nullable=False), sa.Column("canonical_field", sa.String()), sa.Column("method", sa.String(), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("auto_applied", sa.Boolean(), nullable=False))
    op.create_index("ix_schemamapping_run_id", "schemamapping", ["run_id"])
    op.create_table("catalogrecord", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("uploadbatch.id"), nullable=False), sa.Column("row_index", sa.Integer(), nullable=False), sa.Column("raw_values", sa.String(), nullable=False), sa.Column("canonical_values", sa.String(), nullable=False), sa.Column("normalization_trace", sa.String(), nullable=False), sa.Column("quality_components", sa.String(), nullable=False), sa.Column("validation_errors", sa.String(), nullable=False), sa.Column("sku", sa.String()), sa.Column("original_product_name", sa.String()), sa.Column("original_category", sa.String()), sa.Column("original_price", sa.String()), sa.Column("original_inventory", sa.String()), sa.Column("original_tags", sa.String()), sa.Column("cleaned_product_name", sa.String()), sa.Column("cleaned_description", sa.String()), sa.Column("cleaned_category", sa.String()), sa.Column("cleaned_price", sa.Float()), sa.Column("cleaned_currency", sa.String()), sa.Column("cleaned_inventory", sa.Integer()), sa.Column("cleaned_tags", sa.String()), sa.Column("automation_confidence", sa.Float(), nullable=False), sa.Column("confidence_score", sa.Float(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("recommended_action", sa.String(), nullable=False), sa.Column("issue_reasons", sa.String(), nullable=False), sa.Column("severity", sa.String(), nullable=False), sa.Column("review_status", sa.String(), nullable=False), sa.Column("reviewed_at", sa.DateTime()), sa.Column("reviewer_decision", sa.String()), sa.Column("corrected_values", sa.String(), nullable=False), sa.Column("reviewed", sa.Boolean(), nullable=False), sa.Column("exportable", sa.Boolean(), nullable=False), sa.Column("duplicate_of_record_id", sa.Integer(), sa.ForeignKey("catalogrecord.id")), sa.Column("duplicate_method", sa.String()), sa.Column("duplicate_confidence", sa.Float()))
    op.create_index("ix_catalogrecord_batch_id", "catalogrecord", ["batch_id"])
    op.create_index("ix_catalogrecord_sku", "catalogrecord", ["sku"])
    op.create_table("reviewitem", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("record_id", sa.Integer(), sa.ForeignKey("catalogrecord.id"), nullable=False), sa.Column("reason", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("automated_confidence", sa.Float(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("reviewed_at", sa.DateTime()), sa.Column("decision", sa.String()), sa.Column("corrected_values", sa.String(), nullable=False))
    op.create_index("ix_reviewitem_record_id", "reviewitem", ["record_id"])
    op.create_table("schemadriftreport", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("uploadbatch.id"), nullable=False), sa.Column("profiles", sa.String(), nullable=False), sa.Column("missing_columns", sa.String(), nullable=False), sa.Column("unexpected_columns", sa.String(), nullable=False), sa.Column("suggested_mappings", sa.String(), nullable=False), sa.Column("auto_applied_mappings", sa.String(), nullable=False), sa.Column("unresolved_mappings", sa.String(), nullable=False), sa.Column("drift_severity", sa.String(), nullable=False))
    op.create_index("ix_schemadriftreport_batch_id", "schemadriftreport", ["batch_id"])
    op.create_table("export", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("uploadbatch.id")), sa.Column("export_type", sa.String(), nullable=False), sa.Column("row_count", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_export_batch_id", "export", ["batch_id"])
    if legacy:
        op.execute(sa.text("""
            INSERT INTO uploadbatch (id, merchant_id, filename, uploaded_at, total_records, auto_approved_count,
                needs_review_count, duplicate_count, invalid_count, average_confidence, schema_drift_detected, status)
            SELECT id, NULL, filename, uploaded_at, total_records, auto_approved_count, needs_review_count,
                duplicate_count, invalid_count, average_confidence, schema_drift_detected, 'completed'
            FROM legacy_catalogupload
        """))
        op.execute(sa.text("""
            INSERT INTO catalogrecord (id, batch_id, row_index, raw_values, canonical_values, normalization_trace,
                quality_components, validation_errors, sku, original_product_name, original_category, original_price,
                original_inventory, original_tags, cleaned_product_name, cleaned_description, cleaned_category,
                cleaned_price, cleaned_currency, cleaned_inventory, cleaned_tags, automation_confidence,
                confidence_score, status, recommended_action, issue_reasons, severity, review_status, reviewed_at,
                reviewer_decision, corrected_values, reviewed, exportable, duplicate_of_record_id, duplicate_method,
                duplicate_confidence)
            SELECT id, upload_id, id, '{}', '{}', '[]', '{}', '[]', NULL, original_product_name,
                original_category, original_price, original_inventory, original_tags, cleaned_product_name, NULL,
                cleaned_category, cleaned_price, NULL, cleaned_inventory, cleaned_tags, confidence_score / 100.0,
                confidence_score, status, recommended_action, issue_reasons, severity,
                CASE WHEN reviewed = 1 THEN 'approved' WHEN status = 'Auto-approved' THEN 'not_required' ELSE 'pending' END,
                NULL, CASE WHEN reviewed = 1 THEN 'approved' ELSE NULL END, '{}', reviewed, exportable,
                NULL, NULL, NULL
            FROM legacy_catalogrecord
        """))
        op.execute(sa.text("""
            INSERT INTO schemadriftreport (id, batch_id, profiles, missing_columns, unexpected_columns,
                suggested_mappings, auto_applied_mappings, unresolved_mappings, drift_severity)
            SELECT id, upload_id, '[]', missing_columns, unexpected_columns, suggested_mappings,
                auto_applied_mappings, unresolved_mappings, drift_severity
            FROM legacy_schemadriftreport
        """))
        op.execute(sa.text("""
            INSERT INTO reviewitem (record_id, reason, status, automated_confidence, created_at,
                reviewed_at, decision, corrected_values)
            SELECT id, issue_reasons, 'pending', confidence_score / 100.0, CURRENT_TIMESTAMP, NULL, NULL, '{}'
            FROM legacy_catalogrecord WHERE reviewed = 0 AND status != 'Auto-approved'
        """))
        op.drop_table("legacy_catalogrecord")
        op.drop_table("legacy_schemadriftreport")
        op.drop_table("legacy_catalogupload")


def downgrade() -> None:
    for table in ("export", "schemadriftreport", "reviewitem", "catalogrecord", "schemamapping", "processingrun", "uploadbatch", "merchant"):
        op.drop_table(table)
