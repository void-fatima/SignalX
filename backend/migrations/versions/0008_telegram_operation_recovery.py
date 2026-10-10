"""Add leases for recoverable Telegram draft and send operations."""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "telegram_deliveries",
        sa.Column("operation_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "telegram_deliveries",
        sa.Column("operation_token", sa.String(36), nullable=True),
    )
    # Give any operation from the old application version a full lease window
    # to finish before the new version considers it abandoned.
    op.execute(sa.text(
        "UPDATE telegram_deliveries "
        "SET operation_started_at = CURRENT_TIMESTAMP "
        "WHERE state = 'sending' OR draft_busy = TRUE"
    ))


def downgrade():
    op.drop_column("telegram_deliveries", "operation_token")
    op.drop_column("telegram_deliveries", "operation_started_at")
