"""Offline regressions for missing safeguards from the original failure handling."""
from contextlib import closing
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.agents.contracts import RunConfig
from app.agents.providers.base import ProviderError
from app.core.config import settings
from app.core.errors import AppError
from app.models import AnalysisRun, ImportBatch, Message, Product, User, utcnow
from app.schemas.api import ProductOut, RunInput
from app.services import analysis_service as service


PROFILE = {"name": "SensorWorks", "description": "Calibration and repairs for precision sensors.",
           "target_customer": "Laboratories that need reliable measurements."}
PRIVATE_MARKER = "synthetic-private-error-detail"


@pytest.fixture
def sources(client, factory):
    owner = client.get("/api/v1/auth/me").json()["id"]
    with factory() as session:
        other = User(email="other-run-owner@example.test", password_hash="unused-offline-fixture")
        session.add(other)
        session.flush()
        product = Product(user_id=owner, **PROFILE, problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        alternative = Product(user_id=owner, **{**PROFILE, "name": "Alternative service"},
                              problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        foreign_product = Product(user_id=other.id, **PROFILE, problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        batch = ImportBatch(user_id=owner, community_name="laboratory", filename="offline.csv", checksum="a" * 64, row_count=2)
        foreign_batch = ImportBatch(user_id=other.id, community_name="laboratory", filename="offline.csv", checksum="a" * 64, row_count=0)
        session.add_all([product, alternative, foreign_product, batch, foreign_batch])
        session.flush()
        for index in range(2):
            content = "I need sensor calibration. Can anyone recommend a service?"
            session.add(Message(batch_id=batch.id, external_id=str(index), conversation_id="lab",
                                author="Alex", content=content, normalized_content=content, timestamp=utcnow()))
        session.commit()
        return SimpleNamespace(owner=owner, other=other.id, product=product.id, alternative=alternative.id,
                               batch=batch.id, foreign_product=foreign_product.id, foreign_batch=foreign_batch.id,
                               payload=RunInput(product_id=product.id, batch_id=batch.id))


def make_run(session, sources, key, *, winner="matching"):
    user_id = sources.other if winner == "foreign" else sources.owner
    product_id = sources.foreign_product if winner == "foreign" else sources.product
    batch_id = sources.foreign_batch if winner == "foreign" else sources.batch
    if winner == "conflicting":
        product_id = sources.alternative
    product = session.get(Product, product_id)
    run = AnalysisRun(user_id=user_id, product_id=product_id, batch_id=batch_id,
                      product_snapshot=ProductOut.model_validate(product).model_dump(mode="json", exclude={"created_at"}),
                      config_snapshot=RunConfig().model_dump(), idempotency_key=key, total_count=2)
    session.add(run)
    session.commit()
    return run.id


def sqlite_integrity_error(kind="run_key"):
    """Obtain actual SQLite diagnostics, rather than matching a fabricated string."""
    with closing(sqlite3.connect(":memory:")) as db:
        if kind == "run_key":
            db.execute("CREATE TABLE analysis_runs (user_id TEXT, idempotency_key TEXT, UNIQUE(user_id, idempotency_key))")
            db.execute("INSERT INTO analysis_runs VALUES ('owner', 'key')")
            statement = "INSERT INTO analysis_runs VALUES ('owner', 'key')"
        elif kind == "other_unique":
            db.execute("CREATE TABLE other_rows (value TEXT UNIQUE)")
            db.execute("INSERT INTO other_rows VALUES ('same')")
            statement = "INSERT INTO other_rows VALUES ('same')"
        elif kind == "primary_key":
            db.execute("CREATE TABLE analysis_runs (id INTEGER PRIMARY KEY)")
            db.execute("INSERT INTO analysis_runs VALUES (1)")
            statement = "INSERT INTO analysis_runs VALUES (1)"
        elif kind == "not_null":
            db.execute("CREATE TABLE analysis_runs (product_id TEXT NOT NULL)")
            statement = "INSERT INTO analysis_runs VALUES (NULL)"
        else:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("CREATE TABLE products (id INTEGER PRIMARY KEY)")
            db.execute("CREATE TABLE analysis_runs (product_id INTEGER REFERENCES products(id))")
            statement = "INSERT INTO analysis_runs VALUES (999)"
        try:
            db.execute(statement)
        except sqlite3.IntegrityError as original:
            return IntegrityError("INSERT", {}, original)
    pytest.fail("Fixture did not produce an integrity error")


@pytest.mark.parametrize("winner", ["matching", "conflicting", "foreign", "missing"])
def test_create_resolves_only_one_user_scoped_key_race(factory, sources, monkeypatch, winner):
    error = sqlite_integrity_error()
    winner_ids, commits = [], []
    with factory() as session:
        def racing_commit():
            commits.append(1)
            assert len(commits) == 1, "Run creation must never recursively insert again"
            session.rollback()
            if winner != "missing":
                with factory() as concurrent:
                    winner_ids.append(make_run(concurrent, sources, "race-key", winner=winner))
            raise error
        monkeypatch.setattr(session, "commit", racing_commit)
        if winner == "matching":
            result = service.create_run(session, sources.payload, "race-key", sources.owner)
            assert result.id == winner_ids[0] and result.user_id == sources.owner
        else:
            with pytest.raises(AppError) as caught:
                service.create_run(session, sources.payload, "race-key", sources.owner)
            assert caught.value.status == 409
            assert caught.value.code == ("idempotency_conflict" if winner == "conflicting" else "run_conflict")
        assert len(commits) == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisRun)) == len(winner_ids)


@pytest.mark.parametrize("kind", ["other_unique", "primary_key", "not_null", "foreign_key"])
def test_unrelated_integrity_error_never_becomes_idempotent_success(factory, sources, monkeypatch, kind):
    error = sqlite_integrity_error(kind)
    commits = []
    with factory() as session:
        def failing_commit():
            commits.append(1)
            assert len(commits) == 1
            session.rollback()
            # Even a matching row appearing concurrently must not mask a different failure.
            with factory() as concurrent:
                make_run(concurrent, sources, "unrelated-key")
            raise error
        monkeypatch.setattr(session, "commit", failing_commit)
        with pytest.raises(IntegrityError) as caught:
            service.create_run(session, sources.payload, "unrelated-key", sources.owner)
        assert caught.value is error and len(commits) == 1


@pytest.mark.parametrize("constraint,state,expected", [
    ("uq_runs_user_idempotency_key", "23505", True),
    ("analysis_runs_pkey", "23505", False),
    ("other_unique", "23505", False),
    ("uq_runs_user_idempotency_key", "23503", False),
    (None, "23505", False),
])
def test_postgres_constraint_diagnostics_are_fail_closed(constraint, state, expected):
    # Driver-shaped offline diagnostics; this does not claim live PostgreSQL coverage.
    original = RuntimeError(PRIVATE_MARKER)
    original.sqlstate = state
    original.diag = SimpleNamespace(constraint_name=constraint)
    assert service._is_run_key_conflict(IntegrityError("INSERT", {}, original)) is expected


def test_caller_owned_transaction_keeps_flush_failure_and_rollback_ownership(factory, sources, monkeypatch):
    with factory() as session:
        make_run(session, sources, "outer-transaction-key")
        original_scalar = session.scalar
        lookups, rollbacks = [], []
        def hide_initial_lookup(statement, *args, **kwargs):
            if not lookups and statement.column_descriptions[0]["entity"] is AnalysisRun:
                lookups.append(1)
                return None
            return original_scalar(statement, *args, **kwargs)
        monkeypatch.setattr(session, "scalar", hide_initial_lookup)
        original_rollback = session.rollback
        monkeypatch.setattr(session, "rollback", lambda: rollbacks.append(1))
        with pytest.raises(IntegrityError):
            service.create_run(session, sources.payload, "outer-transaction-key", sources.owner, commit=False)
        assert rollbacks == []
        original_rollback()


@pytest.mark.parametrize("error_type", [ProviderError, ValueError])
def test_api_provider_initialization_failure_is_fixed_safe_503(client, factory, sources, monkeypatch, caplog, error_type):
    calls = []
    def unavailable(mode):
        calls.append(mode)
        raise error_type(PRIVATE_MARKER, []) if error_type is ProviderError else error_type(PRIVATE_MARKER)
    monkeypatch.setattr(settings(), "provider_mode", "real")
    monkeypatch.setattr(service, "get_provider", unavailable)
    response = client.post("/api/v1/analysis/runs", json=sources.payload.model_dump(mode="json"),
                           headers={"Idempotency-Key": "unavailable-provider"})
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "provider_configuration_unavailable",
                                        "message": "AI provider configuration is unavailable", "details": []}}
    assert PRIVATE_MARKER not in response.text + caplog.text
    assert calls == ["real"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 0


@pytest.mark.parametrize("field", ["OPENAI_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL"])
def test_actual_avalai_missing_configuration_is_sanitized_without_fallback(client, sources, monkeypatch, field):
    monkeypatch.setattr(settings(), "provider_mode", "real")
    monkeypatch.setenv("LLM_PROVIDER", "avalai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-offline-config-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.avalai.ir/v1")
    monkeypatch.setenv(field, "" if field != "OPENAI_BASE_URL" else "https://untrusted.invalid")
    real_factory = service.get_provider
    calls = []
    def tracked(mode):
        calls.append(mode)
        return real_factory(mode)
    monkeypatch.setattr(service, "get_provider", tracked)
    response = client.post("/api/v1/analysis/runs", json=sources.payload.model_dump(mode="json"),
                           headers={"Idempotency-Key": "invalid-avalai-config"})
    assert response.status_code == 503 and calls == ["real"]
    assert response.json()["error"]["code"] == "provider_configuration_unavailable"
    assert "fake-offline-config-key" not in response.text and "untrusted.invalid" not in response.text


def test_existing_run_replay_keeps_id_even_when_provider_config_is_unavailable(client, factory, sources, monkeypatch):
    with factory() as session:
        run_id = make_run(session, sources, "existing-run-key")
    monkeypatch.setattr(service, "get_provider", lambda _: pytest.fail("Replay must not reinitialize the provider"))
    response = client.post("/api/v1/analysis/runs", json=sources.payload.model_dump(mode="json"),
                           headers={"Idempotency-Key": "existing-run-key"})
    assert response.status_code == 202 and response.json()["id"] == run_id
