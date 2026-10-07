"""Run recovery, ownership, leases and actual usage. Entirely offline."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import select, func

from app.agents.contracts import UsageEvent
from app.agents.providers.base import ProviderError
from app.agents.providers.mock import MockProvider
from app.models import Analysis, AnalysisRun, Message, Usage, utcnow
from app.services.analysis_service import process_one, recover_interrupted, retry_run
from app.core.errors import AppError
from test_flow import authenticated_user, setup_run


class FailedOne(MockProvider):
    def __init__(self, error):
        self.error = error

    def qualify(self, product, target, context):
        if target.external_id == "m03":
            raise self.error
        return super().qualify(product, target, context)


def retry(client, run_id, key="retry-one"):
    return client.post(f"/api/v1/analysis/runs/{run_id}/retry", headers={"Idempotency-Key": key})


@pytest.mark.parametrize("outcome,category", [
    ("timeout", "provider_timeout"), ("provider_error", "provider_failure"),
    ("invalid_output", "invalid_provider_output"), ("incomplete", "invalid_provider_output"),
    ("refused", "provider_refusal"),
])
def test_failed_provider_is_safe_visible_and_source_preserved(client, factory, outcome, category):
    payload, run = setup_run(client)
    private = "must-never-persist-credential-material"
    assert process_one(factory, FailedOne(ProviderError(private, [UsageEvent(outcome=outcome,
        input_tokens=17, output_tokens=None, cost_usd=None, cost_status="unknown")])))
    response = client.get(f"/api/v1/leads?run_id={run['id']}&status=failed")
    assert response.status_code == 200 and response.json()["total"] == 1
    failed = response.json()["items"][0]
    assert failed["failure_category"] == category and failed["decision"] is None and failed["lead_score"] is None
    assert private not in response.text
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 20
        assert session.get(AnalysisRun, run["id"]).batch_id == payload["batch_id"]
        usage = session.scalar(select(Usage).where(Usage.outcome == outcome))
        assert usage.input_tokens == 17 and usage.output_tokens is None and usage.cost_usd is None
        assert usage.run_attempt_no == 1


def test_successful_retry_keeps_ids_successes_history_and_usage(client, factory):
    _, run = setup_run(client)
    process_one(factory, FailedOne(ProviderError("private", [UsageEvent(outcome="timeout")])))
    with factory() as session:
        previous = {a.message_id: (a.id, a.status, a.lead_score, a.reason) for a in session.scalars(select(Analysis))}
        failed_id = next(values[0] for values in previous.values() if values[1] == "failed")
        old_usage = session.scalar(select(func.count()).select_from(Usage))
        snapshot = session.get(AnalysisRun, run["id"]).product_snapshot
    result = retry(client, run["id"])
    assert result.status_code == 202 and result.json()["status"] == "queued" and result.json()["attempt_no"] == 2
    assert result.json()["processed_count"] == 19 and result.json()["failed_count"] == 0
    assert retry(client, run["id"]).json()["attempt_no"] == 2
    assert retry(client, run["id"], "another-key").status_code == 409
    assert process_one(factory)
    assert not process_one(factory)
    recovered = client.get(f"/api/v1/analysis/runs/{run['id']}").json()
    assert recovered["status"] == "completed" and recovered["processed_count"] == 20
    assert retry(client, run["id"]).json()["attempt_no"] == 2
    assert retry(client, run["id"], "new-intent").status_code == 409
    with factory() as session:
        rows = session.scalars(select(Analysis)).all()
        assert len(rows) == 20 and {a.id for a in rows} == {v[0] for v in previous.values()}
        assert all(a.status == "completed" for a in rows)
        for a in rows:
            if a.id != failed_id:
                assert (a.id, a.status, a.lead_score, a.reason) == previous[a.message_id]
        current = session.get(AnalysisRun, run["id"])
        assert current.product_snapshot == snapshot and len(current.retry_history) == 1
        assert current.retry_history[0]["failures"][0]["analysis_id"] == failed_id
        assert session.scalar(select(func.count()).select_from(Usage)) == old_usage + 1
        assert session.scalar(select(Usage).where(Usage.run_attempt_no == 2)).analysis_id == failed_id


def test_retry_is_manual_bounded_and_old_key_cannot_requeue_later_failure(client, factory):
    _, run = setup_run(client)
    provider = FailedOne(ProviderError("private", []))
    process_one(factory, provider)
    assert not process_one(factory)
    assert retry(client, run["id"]).status_code == 202
    process_one(factory, provider)
    assert retry(client, run["id"]).json()["status"] == "partial"
    assert not process_one(factory)
    assert retry(client, run["id"], "second-intent").json()["attempt_no"] == 3


def test_retry_auth_and_ownership_even_for_replayed_key(client, factory):
    _, run = setup_run(client)
    process_one(factory, FailedOne(ProviderError("private", [])))
    assert retry(client, run["id"]).status_code == 202
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert retry(client, run["id"]).status_code == 401
    assert client.post("/api/v1/auth/register", json={"email": "other@example.test", "password": "offline-test-password"}).status_code == 201
    assert retry(client, run["id"]).status_code == 404


@pytest.mark.parametrize("key", ["", " ", "x" * 201])
def test_invalid_retry_key(client, key):
    _, run = setup_run(client)
    assert retry(client, run["id"], key).status_code == 422


def test_snapshot_failure_stays_safe_and_visible(client, factory):
    _, run = setup_run(client)
    with factory() as session:
        session.get(AnalysisRun, run["id"]).product_snapshot = {"invalid": "private-value"}
        session.commit()
    assert process_one(factory)
    failed = client.get(f"/api/v1/leads?run_id={run['id']}&status=failed&limit=100")
    assert failed.json()["total"] == 20 and "private-value" not in failed.text
    assert all(a["failure_category"] == "internal_analysis_failure" for a in failed.json()["items"])
    assert client.get(f"/api/v1/analysis/runs/{run['id']}").json()["status"] == "failed"


def test_internal_exception_text_never_persists(client, factory):
    _, run = setup_run(client)
    process_one(factory, FailedOne(RuntimeError("private-token-material")))
    result = client.get(f"/api/v1/leads?run_id={run['id']}&status=failed")
    assert result.json()["items"][0]["failure_category"] == "internal_analysis_failure"
    assert "private-token-material" not in result.text


def test_worker_claim_prevents_concurrent_duplicate_analysis(client, factory):
    _, run = setup_run(client)
    entered, release = Event(), Event()
    class Blocking(MockProvider):
        def qualify(self, product, target, context):
            entered.set()
            assert release.wait(10)
            return super().qualify(product, target, context)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(process_one, factory, Blocking())
        try:
            assert entered.wait(10)
            assert not process_one(factory)
            assert retry(client, run["id"]).status_code == 409
        finally:
            release.set()
        assert task.result(timeout=10)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis)) == 20


def test_stale_worker_cannot_overwrite_retry_and_late_usage_is_saved(client, factory):
    _, run = setup_run(client)
    entered, release = Event(), Event()
    class Blocking(MockProvider):
        def qualify(self, product, target, context):
            entered.set()
            assert release.wait(10)
            return super().qualify(product, target, context)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(process_one, factory, Blocking())
        try:
            assert entered.wait(10)
            with factory() as session:
                session.get(AnalysisRun, run["id"]).heartbeat_at = utcnow() - timedelta(minutes=10)
                session.commit()
            recover_interrupted(factory)
            assert retry(client, run["id"]).json()["attempt_no"] == 2
        finally:
            release.set()
        assert task.result(timeout=10)
    with factory() as session:
        assert session.get(AnalysisRun, run["id"]).status == "queued"
        assert session.scalar(select(Usage).where(Usage.run_attempt_no == 1)) is not None
    assert process_one(factory)
    assert client.get(f"/api/v1/analysis/runs/{run['id']}").json()["status"] == "completed"


def test_retry_compare_and_swap_rejects_stale_competing_intent(client, factory):
    _, run = setup_run(client)
    process_one(factory, FailedOne(ProviderError("private", [])))
    with factory() as first, factory() as stale:
        original = stale.get(AnalysisRun, run["id"])
        from app.models import Product
        user_id = stale.get(Product, original.product_id).owner_user_id
        assert retry_run(first, run["id"], user_id, "first").attempt_no == 2
        with pytest.raises(AppError) as error:
            retry_run(stale, run["id"], user_id, "different")
        assert error.value.status == 409
    assert retry(client, run["id"], "first").json()["attempt_no"] == 2


def test_factory_failure_records_saved_sources_without_fallback(client, factory, monkeypatch):
    _, run = setup_run(client)
    calls = []
    def unavailable(mode):
        calls.append(mode)
        raise ProviderError("fake-configuration-secret", [])
    monkeypatch.setattr("app.services.analysis_service.get_provider", unavailable)
    assert process_one(factory)
    failed = client.get(f"/api/v1/leads?run_id={run['id']}&status=failed&limit=100")
    assert failed.json()["total"] == 20 and "fake-configuration-secret" not in failed.text
    assert calls == ["mock"]  # Exactly the configured factory selection; no second provider.
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Usage)) == 0
        assert session.scalar(select(func.count()).select_from(Message)) == 20


def test_worker_database_outage_survives_and_logs_no_connection_secrets(monkeypatch, caplog):
    from sqlalchemy.exc import OperationalError
    from app import worker
    class StopWorker(Exception):
        pass
    calls = []
    def unavailable(factory):
        calls.append("recovery")
        raise OperationalError("SQL containing private-connection-secret", {}, RuntimeError("private-connection-secret"))
    def stop(delay):
        calls.append("pause")
        raise StopWorker()
    monkeypatch.setattr(worker, "recover_interrupted", unavailable)
    monkeypatch.setattr(worker.time, "sleep", stop)
    with pytest.raises(StopWorker):
        worker.main()
    assert calls == ["recovery", "pause"]
    assert "database unavailable" in caplog.text and "private-connection-secret" not in caplog.text
