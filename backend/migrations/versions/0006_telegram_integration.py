"""Add Telegram integration tables with Backend user ownership."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0006"
down_revision = "0005"
branch_labels = depends_on = None


def upgrade():
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "telegram_chat_mappings",
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_telegram_chat_mappings_owner_user_id_users"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_telegram_chat_mappings_product_id_products"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_chat_id", name="uq_telegram_chat_mappings_telegram_chat_id"),
    )
    op.create_index(
        "ix_telegram_chat_mappings_owner_user_id",
        "telegram_chat_mappings",
        ["owner_user_id"],
    )

    op.create_table(
        "telegram_receipts",
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("mapping_id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("source_metadata", json_type, nullable=False),
        sa.Column("agent_input", json_type, nullable=True),
        sa.Column("agent_output", json_type, nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mapping_id"], ["telegram_chat_mappings.id"], name="fk_telegram_receipts_mapping_id_telegram_chat_mappings"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], name="fk_telegram_receipts_message_id_messages"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name="fk_telegram_receipts_run_id_analysis_runs"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_chat_id", "telegram_message_id", name="uq_telegram_receipts_chat_message"),
        sa.UniqueConstraint("update_id", name="uq_telegram_receipts_update_id"),
        sa.UniqueConstraint("message_id", name="uq_telegram_receipts_message_id"),
        sa.UniqueConstraint("run_id", name="uq_telegram_receipts_run_id"),
    )

    op.create_table(
        "telegram_deliveries",
        sa.Column("analysis_id", sa.String(36), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("approved_text", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(36), nullable=True),
        sa.Column("sent_message_id", sa.BigInteger(), nullable=True),
        sa.Column("failure_category", sa.String(50), nullable=True),
        sa.Column("delivery_uncertain", sa.Boolean(), nullable=False),
        sa.Column("draft_busy", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], name="fk_telegram_deliveries_analysis_id_analyses"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name="fk_telegram_deliveries_approved_by_users"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", name="uq_telegram_deliveries_analysis_id"),
    )


def downgrade():
    op.drop_table("telegram_deliveries")
    op.drop_table("telegram_receipts")
    op.drop_index("ix_telegram_chat_mappings_owner_user_id", table_name="telegram_chat_mappings")
    op.drop_table("telegram_chat_mappings")
