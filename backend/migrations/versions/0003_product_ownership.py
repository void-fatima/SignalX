"""Persistent sessions and owner-scoped products/imports; retain historical data."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None

NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s"}


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False))
    op.create_table("auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("import_batches")
    old_name = next(c["name"] for c in constraints if c["column_names"] == ["community_name", "checksum"])
    for table in ("products", "import_batches"):
        with op.batch_alter_table(table, naming_convention=NAMING) as batch:
            batch.add_column(sa.Column("owner_user_id", sa.String(36), nullable=True))
            batch.create_foreign_key(f"fk_{table}_owner", "users", ["owner_user_id"], ["id"])
            batch.create_index(f"ix_{table}_owner_user_id", ["owner_user_id"])
            if table == "import_batches":
                batch.drop_constraint(old_name or "uq_import_batches_community_name_checksum", type_="unique")
                batch.create_unique_constraint("uq_import_batches_owner_content", ["owner_user_id", "community_name", "checksum"])


def downgrade():
    # Reverting to global deduplication must never discard different users' imports.
    duplicates = op.get_bind().execute(sa.text(
        "SELECT 1 FROM import_batches GROUP BY community_name, checksum HAVING COUNT(*) > 1")).first()
    if duplicates:
        raise RuntimeError("Cannot downgrade: owner-scoped imports conflict with the historical global uniqueness constraint")
    for table in ("import_batches", "products"):
        with op.batch_alter_table(table) as batch:
            if table == "import_batches":
                batch.drop_constraint("uq_import_batches_owner_content", type_="unique")
                batch.create_unique_constraint("uq_import_batches_community_name_checksum", ["community_name", "checksum"])
            batch.drop_index(f"ix_{table}_owner_user_id")
            batch.drop_constraint(f"fk_{table}_owner", type_="foreignkey")
            batch.drop_column("owner_user_id")
    op.drop_table("auth_sessions")
    op.drop_table("users")
