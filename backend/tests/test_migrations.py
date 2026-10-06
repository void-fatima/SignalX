import os
from pathlib import Path
import sqlite3
import subprocess
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_auth_migration_can_downgrade_sqlite_without_leftover_temp_tables(tmp_path):
    database = tmp_path / "migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}

    for operation in (("upgrade", "head"), ("downgrade", "0001")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *operation],
            cwd=BACKEND_ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        analysis_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(analysis_runs)")}
        indexes = {
            index[1]
            for table in ("analysis_runs", "import_batches", "products")
            for index in connection.execute(f"PRAGMA index_list({table})")
        }

    assert not any(name.startswith("_alembic_tmp_") for name in tables)
    assert "user_id" not in analysis_columns
    assert not indexes.intersection({
        "ix_analysis_runs_user_id", "ix_import_batches_user_id", "ix_products_user_id",
    })
