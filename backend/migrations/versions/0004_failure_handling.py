"""Explicit retry audit and safe failure metadata, after Telegram and ownership.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from app.models import json_type

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analysis_runs", sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("analysis_runs", sa.Column("retry_history", json_type, nullable=False, server_default=sa.text("'[]'")))
    op.add_column("analyses", sa.Column("failure_category", sa.String(50), nullable=True))
    op.add_column("llm_usage", sa.Column("run_attempt_no", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("telegram_deliveries", sa.Column("failure_http_status", sa.Integer(), nullable=True))
    op.add_column("telegram_deliveries", sa.Column("retry_after_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("telegram_deliveries", sa.Column("send_history", json_type, nullable=False, server_default=sa.text("'[]'")))


def downgrade():
    # Downgrade discards only the new audit/metadata fields; original records survive.
    for table, columns in (
        ("telegram_deliveries", ("send_history", "retry_after_at", "failure_http_status")),
        ("llm_usage", ("run_attempt_no",)),
        ("analyses", ("failure_category",)),
        ("analysis_runs", ("retry_history", "attempt_no")),
    ):
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column)
