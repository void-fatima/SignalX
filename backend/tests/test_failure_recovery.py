"""Failure recovery keeps successful results and fences stale worker writes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import func, select

from app.agents.orchestrator import analyze_agent
from app.agents.contracts import UsageInfo
from app.agents.providers.base import ProviderError
from app.agents.providers.mock import MockProvider
from app.core.config import settings
from app.models import Analysis, AnalysisRun, Message, Usage, utcnow
from app.schemas.api import AnalysisOut, RunOut
from app.integrations.telegram.schemas import DeliveryOut
from app.services.analysis_service import process_one, recover_interrupted


DATA = Path(__file__).resolve().parents[2] / "data" / "demo_messages.csv"
PRODUCT = {"name": "Backend course", "description": "Project-based backend course", "target_customer": "Developers"}


def setup_run(client, key="failure-recovery"):
    product = client.post("/api/v1/products", json=PRODUCT)
    assert product.status_code == 201
    batch = client.post("/api/v1/imports", data={"community_name": "recovery"},
        files={"file": ("demo.csv", DATA.read_bytes(), "text/csv")})
    assert batch.status_code == 201
    payload = {"product_id": product.json()["id"], "batch_id": batch.json()["batch"]["id"]}
    run = client.post("/api/v1/analysis/runs", json=payload, headers={"Idempotency-Key": key})
    assert run.status_code == 202
    return run.json()


def retry(client, run_id, key="retry-once"):
    return client.post(f"/api/v1/analysis/runs/{run_id}/retry", headers={"Idempotency-Key": key})


def _failure_usage(outcome="timeout"):
    return UsageInfo(stage="qualification", attempt_no=1, provider_mode="mock", model="offline-test",
        input_tokens=None, output_tokens=None, estimated_cost=0, cost_status="mock",
        price_version=None, latency_ms=0, outcome=outcome)


def test_native_agent_retry_preserves_ids_outputs_usage_and_safe_failure(client, factory):
    run = setup_run(client)
    secret_text = "private-provider-response-must-not-be-persisted"
    with factory() as session:
        target = session.scalar(select(Message).where(
            Message.batch_id == run["batch_id"], Message.external_id == "m03"))
        failed_message_id = target.id
    should_fail = True

    def fail_once(agent_input):
        nonlocal should_fail
        if agent_input.message.id == failed_message_id and should_fail:
            should_fail = False
            raise ProviderError(secret_text, [_failure_usage()])
        return analyze_agent(agent_input)

    assert process_one(factory, agent_orchestrator=fail_once)
    failed = client.get(f"/api/v1/leads?run_id={run['id']}&status=failed")
    assert failed.status_code == 200 and failed.json()["total"] == 1
    assert failed.json()["items"][0]["failure_category"] == "provider_timeout"
    assert secret_text not in failed.text

    with factory() as session:
        before = {row.message_id: (row.id, row.status, row.agent_output) for row in session.scalars(
            select(Analysis).where(Analysis.run_id == run["id"]))}
        original_successes = {message_id: value for message_id, value in before.items() if value[1] == "completed"}
        original_failed_id = before[failed_message_id][0]
        original_usage_count = session.scalar(select(func.count()).select_from(Usage).where(Usage.run_id == run["id"]))

    accepted = retry(client, run["id"])
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued" and accepted.json()["attempt_no"] == 2
    assert accepted.json()["processed_count"] == run["total_count"] - 1
    assert retry(client, run["id"]).json()["attempt_no"] == 2
    assert retry(client, run["id"], "competing-key").status_code == 409
    assert process_one(factory, agent_orchestrator=analyze_agent)
    assert retry(client, run["id"]).json()["status"] == "completed"
    assert retry(client, run["id"], "after-completion").status_code == 409

    with factory() as session:
        rows = {row.message_id: row for row in session.scalars(select(Analysis).where(Analysis.run_id == run["id"]))}
        assert set(rows) == set(before)
        assert len(rows) == run["total_count"]
        assert all(row.status == "completed" and row.agent_output for row in rows.values())
        assert rows[failed_message_id].id == original_failed_id
        for message_id, (analysis_id, status, output) in original_successes.items():
            assert rows[message_id].id == analysis_id
            assert rows[message_id].agent_output == output
        assert session.scalar(select(func.count()).select_from(Usage).where(Usage.run_id == run["id"])) == original_usage_count + 1
        assert session.scalar(select(Usage).where(Usage.run_id == run["id"],
            Usage.run_attempt_no == 1, Usage.outcome == "timeout")).outcome == "timeout"
        assert session.scalar(select(Usage).where(Usage.run_id == run["id"], Usage.run_attempt_no == 2)) is not None


def test_worker_claim_and_retry_reject_active_run(client, factory):
    run = setup_run(client, "worker-claim")
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
            assert process_one(factory, MockProvider()) is False
            assert retry(client, run["id"]).status_code == 409
        finally:
            release.set()
        assert task.result(timeout=20)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis).where(Analysis.run_id == run["id"])) == run["total_count"]


def test_stale_worker_keeps_late_usage_but_cannot_write_old_result(client, factory, monkeypatch):
    run = setup_run(client, "stale-worker")
    entered, release = Event(), Event()
    monkeypatch.setattr(settings(), "heartbeat_timeout_seconds", 1)

    class Blocking(MockProvider):
        def qualify(self, product, target, context):
            entered.set()
            blocked_message_id.append(target.id)
            assert release.wait(10)
            return super().qualify(product, target, context)

    blocked_message_id = []

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(process_one, factory, Blocking())
        try:
            assert entered.wait(10)
            with factory() as session:
                session.get(AnalysisRun, run["id"]).heartbeat_at = utcnow() - timedelta(seconds=10)
                session.commit()
                completed_before = session.scalar(select(func.count()).select_from(Analysis).where(
                    Analysis.run_id == run["id"], Analysis.status == "completed"))
            recover_interrupted(factory)
            accepted = retry(client, run["id"])
            assert accepted.status_code == 202 and accepted.json()["attempt_no"] == 2
        finally:
            release.set()
        assert task.result(timeout=20)

    with factory() as session:
        current = session.get(AnalysisRun, run["id"])
        assert current.status == "queued" and current.attempt_no == 2
        assert session.scalar(select(func.count()).select_from(Analysis).where(
            Analysis.run_id == run["id"], Analysis.message_id == blocked_message_id[0])) == 0
        assert session.scalar(select(func.count()).select_from(Analysis).where(
            Analysis.run_id == run["id"], Analysis.status == "completed")) == completed_before
        late = session.scalar(select(Usage).where(Usage.run_id == run["id"], Usage.run_attempt_no == 1))
        assert late is not None
    assert process_one(factory, MockProvider())
    assert client.get(f"/api/v1/analysis/runs/{run['id']}").json()["status"] == "completed"


@pytest.mark.parametrize(("outcome", "category"), [
    ("timeout", "provider_timeout"),
    ("provider_error", "provider_failure"),
    ("invalid_output", "invalid_provider_output"),
    ("incomplete", "invalid_provider_output"),
    ("refused", "provider_refusal"),
])
def test_failure_category_allowlist(client, factory, outcome, category):
    run = setup_run(client, f"category-{outcome}")

    def failing_agent(_inputs):
        raise ProviderError("do-not-persist-this", [_failure_usage(outcome)])

    assert process_one(factory, agent_orchestrator=failing_agent)
    rows = client.get(f"/api/v1/leads?run_id={run['id']}&status=failed&limit=100").json()
    assert rows["total"] == run["total_count"]
    assert {row["failure_category"] for row in rows["items"]} == {category}
    assert "do-not-persist-this" not in str(rows)


def test_shared_failure_fixtures_validate():
    root = Path(__file__).resolve().parents[2] / "contracts" / "examples"
    RunOut.model_validate(json.loads((root / "failed_run.json").read_text(encoding="utf-8")))
    AnalysisOut.model_validate(json.loads((root / "failed_lead.json").read_text(encoding="utf-8")))
    DeliveryOut.model_validate(json.loads((root / "failed_telegram_delivery.json").read_text(encoding="utf-8")))
