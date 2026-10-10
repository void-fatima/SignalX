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


def test_response_feedback_migration_is_reversible_on_sqlite(tmp_path):
    database = tmp_path / "response-feedback.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    for operation in (("upgrade", "head"), ("downgrade", "0004")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *operation],
            cwd=BACKEND_ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        if operation[0] == "upgrade":
            with sqlite3.connect(database) as connection:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                assert {"suggested_responses", "lead_feedback"} <= tables

    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "suggested_responses" not in tables and "lead_feedback" not in tables


def test_telegram_migration_references_backend_users_for_mapping_and_approval(tmp_path):
    database = tmp_path / "telegram-ownership.db"
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
        mapping_fks = {
            (row[2], row[3], row[4])
            for row in connection.execute("PRAGMA foreign_key_list(telegram_chat_mappings)")
        }
        delivery_fks = {
            (row[2], row[3], row[4])
            for row in connection.execute("PRAGMA foreign_key_list(telegram_deliveries)")
        }
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert ("users", "owner_user_id", "id") in mapping_fks
    assert ("products", "product_id", "id") in mapping_fks
    assert ("users", "approved_by", "id") in delivery_fks
    assert {"telegram_chat_mappings", "telegram_receipts", "telegram_deliveries"} <= tables
    assert revision == "0009"


def test_failure_recovery_migration_preserves_rows_and_adds_only_seven_fields(tmp_path):
    database = tmp_path / "failure-recovery.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0006"],
        cwd=BACKEND_ROOT, env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO analysis_runs (id, created_at, product_id, batch_id, product_snapshot, "
            "config_snapshot, idempotency_key, status, total_count, processed_count, failed_count, error) "
            "VALUES ('run', '2026-10-08T00:00:00', 'product', 'batch', '{}', '{}', 'key', 'failed', 1, 1, 1, 'safe prior error')"
        )
        connection.execute(
            "INSERT INTO analyses (id, created_at, run_id, message_id, status, is_candidate, "
            "screening_reason, reason, evidence, context_message_ids, limitations, scoring_version, "
            "prompt_version, provider_mode) VALUES ('analysis', '2026-10-08T00:00:00', 'run', "
            "'message', 'failed', 1, 'processing_error', 'safe prior error', '[]', '[]', '[]', "
            "NULL, NULL, 'real')"
        )
        connection.execute(
            "INSERT INTO llm_usage (id, created_at, run_id, message_id, analysis_id, stage, attempt_no, "
            "provider_mode, cost_status, outcome) VALUES ('usage', '2026-10-08T00:00:00', 'run', "
            "'message', 'analysis', 'qualification', 1, 'real', 'unknown', 'timeout')"
        )
        connection.execute(
            "INSERT INTO telegram_deliveries (id, created_at, analysis_id, state, approved_text, "
            "failure_category, delivery_uncertain, draft_busy) VALUES ('delivery', '2026-10-08T00:00:00', "
            "'analysis', 'failed', 'Human-approved text', 'timeout', 1, 0)"
        )
        connection.commit()

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT, env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(database) as connection:
        run = connection.execute("SELECT attempt_no, retry_history, status, error FROM analysis_runs WHERE id='run'").fetchone()
        analysis = connection.execute("SELECT failure_category, reason FROM analyses WHERE id='analysis'").fetchone()
        usage = connection.execute("SELECT run_attempt_no, outcome FROM llm_usage WHERE id='usage'").fetchone()
        delivery = connection.execute("SELECT failure_http_status, retry_after_at, send_history, approved_text, delivery_uncertain "
            "FROM telegram_deliveries WHERE id='delivery'").fetchone()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert run == (1, "[]", "failed", "safe prior error")
    assert analysis == (None, "safe prior error")
    assert usage == (1, "timeout")
    assert delivery == (None, None, "[]", "Human-approved text", 1)
    assert revision == "0009"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0006"],
        cwd=BACKEND_ROOT, env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(database) as connection:
        columns = {table: {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for table in ("analysis_runs", "analyses", "llm_usage", "telegram_deliveries")}
        assert connection.execute("SELECT approved_text FROM telegram_deliveries WHERE id='delivery'").fetchone()[0] == "Human-approved text"
    assert "attempt_no" not in columns["analysis_runs"]
    assert "retry_history" not in columns["analysis_runs"]
    assert "failure_category" not in columns["analyses"]
    assert "run_attempt_no" not in columns["llm_usage"]
    assert not {"failure_http_status", "retry_after_at", "send_history"}.intersection(columns["telegram_deliveries"])
