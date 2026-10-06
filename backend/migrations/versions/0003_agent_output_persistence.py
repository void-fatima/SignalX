"""Persist complete AgentOutput and preserve unknown usage metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None


def upgrade():
    output_json = sa.JSON().with_variant(JSONB(), "postgresql")
    op.add_column("analyses", sa.Column("agent_output", output_json, nullable=True))
    with op.batch_alter_table("llm_usage") as batch:
        batch.alter_column("model", existing_type=sa.String(100), nullable=True)
        batch.alter_column("price_version", existing_type=sa.String(50), nullable=True)
        batch.alter_column("latency_ms", existing_type=sa.Integer(), nullable=True)


def downgrade():
    # A contract may legitimately persist unknown model/price/latency values.
    # Do not silently invent values when moving back to the old constraints.
    bind = op.get_bind()
    unknown = bind.execute(sa.text(
        "SELECT COUNT(*) FROM llm_usage "
        "WHERE model IS NULL OR price_version IS NULL OR latency_ms IS NULL"
    )).scalar_one()
    if unknown:
        raise RuntimeError(
            "Cannot downgrade 0003 while llm_usage contains unknown metadata; "
            "export or remove those usage rows first"
        )
    with op.batch_alter_table("llm_usage") as batch:
        batch.alter_column("model", existing_type=sa.String(100), nullable=False)
        batch.alter_column("price_version", existing_type=sa.String(50), nullable=False)
        batch.alter_column("latency_ms", existing_type=sa.Integer(), nullable=False)
    op.drop_column("analyses", "agent_output")
