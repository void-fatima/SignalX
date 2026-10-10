"""Add independent discovery records after Telegram recovery 0008; existing lead tables are untouched."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = depends_on = None

def upgrade():
    j = sa.JSON().with_variant(JSONB(), "postgresql")
    common = lambda: [sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False)]
    op.create_table("discovery_searches", *common(),
        sa.Column("source", sa.String(20), nullable=False), sa.Column("idempotency_key", sa.String(200), nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("query", j, nullable=False), sa.Column("product_snapshot", j, nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("results", j, nullable=False), sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(50)), sa.Column("error", sa.Text()), sa.UniqueConstraint("user_id", "idempotency_key", name="uq_discovery_user_key"))
    op.create_index("ix_discovery_user_created", "discovery_searches", ["user_id", "created_at"])
    op.create_table("discovery_prospects", *common(),
        sa.Column("search_id", sa.String(36), sa.ForeignKey("discovery_searches.id"), nullable=False), sa.Column("source", sa.String(20), nullable=False), sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column("title", sa.String(240), nullable=False), sa.Column("url", sa.Text(), nullable=False), sa.Column("excerpt", sa.Text(), nullable=False), sa.Column("location", sa.String(200), nullable=False),
        sa.Column("signal", sa.String(30), nullable=False), sa.Column("explanation", sa.Text(), nullable=False), sa.Column("qualification_status", sa.String(20), nullable=False), sa.Column("qualification_key", sa.String(200)),
        sa.Column("qualification_usage", j, nullable=False), sa.Column("qualification_error", sa.Text()), sa.Column("agent_output", j), sa.UniqueConstraint("user_id", "product_id", "source", "source_id", name="uq_discovery_prospect_source"))
    op.create_index("ix_discovery_prospect_owner", "discovery_prospects", ["user_id", "created_at"])
    op.create_table("discovery_budgets", sa.Column("source", sa.String(20), primary_key=True), sa.Column("last_request_at", sa.DateTime(timezone=True)), sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("request_count", sa.Integer(), nullable=False))

def downgrade():
    op.drop_table("discovery_prospects")
    op.drop_table("discovery_searches")
    op.drop_table("discovery_budgets")
