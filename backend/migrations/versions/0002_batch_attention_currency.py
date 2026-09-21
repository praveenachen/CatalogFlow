"""Add independent attention count and configured batch currency."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0002_batch_attention_currency"
down_revision = "0001_phase1_core"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns("uploadbatch")}


def upgrade() -> None:
    columns = _columns()
    with op.batch_alter_table("uploadbatch") as batch:
        if "attention_count" not in columns:
            batch.add_column(sa.Column("attention_count", sa.Integer(), nullable=False, server_default="0"))
        if "default_currency" not in columns:
            batch.add_column(sa.Column("default_currency", sa.String(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE uploadbatch SET attention_count = "
            "needs_review_count + duplicate_count + invalid_count"
        )
    )
    with op.batch_alter_table("uploadbatch") as batch:
        batch.alter_column("attention_count", server_default=None)


def downgrade() -> None:
    columns = _columns()
    with op.batch_alter_table("uploadbatch") as batch:
        if "default_currency" in columns:
            batch.drop_column("default_currency")
        if "attention_count" in columns:
            batch.drop_column("attention_count")
