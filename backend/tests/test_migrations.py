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


def test_agent_output_migration_is_reversible_on_sqlite(tmp_path):
    database = tmp_path / "agent-output-migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    for operation in (("upgrade", "head"), ("downgrade", "0002")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *operation],
            cwd=BACKEND_ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(database) as connection:
        analysis_columns = {row[1] for row in connection.execute("PRAGMA table_info(analyses)")}
        usage_columns = {row[1]: row[3] for row in connection.execute("PRAGMA table_info(llm_usage)")}
    assert "agent_output" not in analysis_columns
    assert usage_columns["model"] == 1
    assert usage_columns["price_version"] == 1
    assert usage_columns["latency_ms"] == 1


def test_analysis_versions_allow_null_when_stages_do_not_run(tmp_path):
    database = tmp_path / "nullable-analysis-versions.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    with sqlite3.connect(database) as connection:
        columns = {row[1]: row[3] for row in connection.execute("PRAGMA table_info(analyses)")}
        connection.execute(
            "INSERT INTO analyses "
            "(id, created_at, run_id, message_id, status, is_candidate, "
            "screening_reason, reason, evidence, context_message_ids, limitations, "
            "scoring_version, prompt_version, provider_mode) "
            "VALUES ('analysis', '2026-10-06T00:00:00', 'run', 'message', 'completed', 0, "
            "'unrelated', 'unrelated', '[]', '[]', '[]', NULL, NULL, 'real')"
        )
        saved = connection.execute(
            "SELECT scoring_version, prompt_version FROM analyses WHERE id='analysis'"
        ).fetchone()
        assert columns["scoring_version"] == 0
        assert columns["prompt_version"] == 0
        assert saved == (None, None)
