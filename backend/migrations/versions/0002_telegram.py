"""Freeze the additive Telegram schema from the completed integration commit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = depends_on = None


def upgrade():
    names = {"telegram_chat_mappings", "telegram_receipts", "telegram_deliveries"}
    if names.intersection(sa.inspect(op.get_bind()).get_table_names()):
        raise RuntimeError("Telegram tables already exist: verify the SQL handoff and adopt revision 0002 before upgrading; see docs/business-setup.md")
    json = sa.JSON().with_variant(JSONB(), "postgresql")
    def record(name, *columns):
        op.create_table(name, sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), *columns)
    record("telegram_chat_mappings",
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False))
    op.create_index("ix_telegram_chat_mappings_owner_user_id", "telegram_chat_mappings", ["owner_user_id"])
    record("telegram_receipts",
        sa.Column("update_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("mapping_id", sa.String(36), sa.ForeignKey("telegram_chat_mappings.id"), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id"), nullable=False, unique=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"), nullable=False, unique=True),
        sa.Column("source_metadata", json, nullable=False),
        sa.Column("agent_input", json, nullable=True),
        sa.Column("agent_output", json, nullable=True),
        sa.UniqueConstraint("telegram_chat_id", "telegram_message_id"))
    record("telegram_deliveries",
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("analyses.id"), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("approved_text", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(36), nullable=True),
        sa.Column("sent_message_id", sa.BigInteger(), nullable=True),
        sa.Column("failure_category", sa.String(50), nullable=True),
        sa.Column("delivery_uncertain", sa.Boolean(), nullable=False),
        sa.Column("draft_busy", sa.Boolean(), nullable=False))


def downgrade():
    for name in ("telegram_deliveries", "telegram_receipts", "telegram_chat_mappings"):
        op.drop_table(name)
