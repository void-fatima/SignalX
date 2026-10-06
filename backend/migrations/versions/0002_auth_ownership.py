"""Add real accounts, revocable sessions and user-scoped data ownership."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = depends_on = None


def _constraint_name(table: str, columns: list[str]) -> str:
    """Find the existing unique constraint by columns across SQLite/Postgres."""
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints(table):
        if constraint.get("column_names") == columns:
            return constraint.get("name") or f"uq_{table}_{columns[0]}"
    raise RuntimeError(f"Expected unique constraint on {table}({', '.join(columns)})")


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_digest", name="uq_user_sessions_token_digest"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if is_sqlite:
        # SQLite must rebuild both tables to replace their global unique keys.
        with op.get_context().autocommit_block():
            bind.exec_driver_sql("PRAGMA foreign_keys=OFF")

    if is_sqlite:
        with op.batch_alter_table("products") as batch:
            batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_products_user_id_users", "users", ["user_id"], ["id"])
    else:
        op.add_column("products", sa.Column("user_id", sa.String(36), nullable=True))
        op.create_foreign_key("fk_products_user_id_users", "products", "users", ["user_id"], ["id"])
    op.create_index("ix_products_user_id", "products", ["user_id"])

    if is_sqlite:
        naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
        with op.batch_alter_table("import_batches", naming_convention=naming) as batch:
            batch.drop_constraint(_constraint_name("import_batches", ["community_name", "checksum"]), type_="unique")
            batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_import_batches_user_id_users", "users", ["user_id"], ["id"])
            batch.create_unique_constraint("uq_import_user_community_checksum", ["user_id", "community_name", "checksum"])
        with op.batch_alter_table("analysis_runs", naming_convention=naming) as batch:
            batch.drop_constraint(_constraint_name("analysis_runs", ["idempotency_key"]), type_="unique")
            batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_analysis_runs_user_id_users", "users", ["user_id"], ["id"])
            batch.create_unique_constraint("uq_runs_user_idempotency_key", ["user_id", "idempotency_key"])
        with op.get_context().autocommit_block():
            bind.exec_driver_sql("PRAGMA foreign_keys=ON")
    else:
        op.drop_constraint(_constraint_name("import_batches", ["community_name", "checksum"]), "import_batches", type_="unique")
        op.add_column("import_batches", sa.Column("user_id", sa.String(36), nullable=True))
        op.create_foreign_key("fk_import_batches_user_id_users", "import_batches", "users", ["user_id"], ["id"])
        op.create_unique_constraint("uq_import_user_community_checksum", "import_batches", ["user_id", "community_name", "checksum"])

        op.drop_constraint(_constraint_name("analysis_runs", ["idempotency_key"]), "analysis_runs", type_="unique")
        op.add_column("analysis_runs", sa.Column("user_id", sa.String(36), nullable=True))
        op.create_foreign_key("fk_analysis_runs_user_id_users", "analysis_runs", "users", ["user_id"], ["id"])
        op.create_unique_constraint("uq_runs_user_idempotency_key", "analysis_runs", ["user_id", "idempotency_key"])

    op.create_index("ix_import_batches_user_id", "import_batches", ["user_id"])
    op.create_index("ix_analysis_runs_user_id", "analysis_runs", ["user_id"])


def downgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if is_sqlite:
        with op.get_context().autocommit_block():
            bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    # Drop ownership indexes before either dropping user_id (Postgres) or
    # rebuilding tables (SQLite), where batch mode would otherwise recreate
    # the indexes on temporary tables that no longer have user_id.
    op.drop_index("ix_analysis_runs_user_id", table_name="analysis_runs")
    op.drop_index("ix_import_batches_user_id", table_name="import_batches")
    op.drop_index("ix_products_user_id", table_name="products")

    if is_sqlite:
        naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
        with op.batch_alter_table("analysis_runs", naming_convention=naming) as batch:
            batch.drop_constraint("uq_runs_user_idempotency_key", type_="unique")
            batch.drop_column("user_id")
            batch.create_unique_constraint("uq_analysis_runs_idempotency_key", ["idempotency_key"])
        with op.batch_alter_table("import_batches", naming_convention=naming) as batch:
            batch.drop_constraint("uq_import_user_community_checksum", type_="unique")
            batch.drop_column("user_id")
            batch.create_unique_constraint("uq_import_batches_community_name", ["community_name", "checksum"])
    else:
        op.drop_constraint("uq_runs_user_idempotency_key", "analysis_runs", type_="unique")
        op.drop_constraint("fk_analysis_runs_user_id_users", "analysis_runs", type_="foreignkey")
        op.drop_column("analysis_runs", "user_id")
        op.create_unique_constraint("uq_analysis_runs_idempotency_key", "analysis_runs", ["idempotency_key"])

        op.drop_constraint("uq_import_user_community_checksum", "import_batches", type_="unique")
        op.drop_constraint("fk_import_batches_user_id_users", "import_batches", type_="foreignkey")
        op.drop_column("import_batches", "user_id")
        op.create_unique_constraint("uq_import_batches_community_name", "import_batches", ["community_name", "checksum"])

    if is_sqlite:
        with op.batch_alter_table("products") as batch:
            batch.drop_constraint("fk_products_user_id_users", type_="foreignkey")
            batch.drop_column("user_id")
    else:
        op.drop_constraint("fk_products_user_id_users", "products", type_="foreignkey")
        op.drop_column("products", "user_id")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
    if is_sqlite:
        with op.get_context().autocommit_block():
            bind.exec_driver_sql("PRAGMA foreign_keys=ON")
