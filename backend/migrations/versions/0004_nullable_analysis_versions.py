"""Allow missing prompt/scoring versions when the corresponding stage did not run."""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("analyses") as batch:
        batch.alter_column(
            "scoring_version", existing_type=sa.String(50), nullable=True
        )
        batch.alter_column(
            "prompt_version", existing_type=sa.String(50), nullable=True
        )


def downgrade():
    bind = op.get_bind()
    missing_versions = bind.execute(sa.text(
        "SELECT COUNT(*) FROM analyses "
        "WHERE scoring_version IS NULL OR prompt_version IS NULL"
    )).scalar_one()
    if missing_versions:
        raise RuntimeError(
            "Cannot downgrade 0004 while analyses contain null stage versions; "
            "export or remove those analyses first"
        )
    with op.batch_alter_table("analyses") as batch:
        batch.alter_column(
            "scoring_version", existing_type=sa.String(50), nullable=False
        )
        batch.alter_column(
            "prompt_version", existing_type=sa.String(50), nullable=False
        )
