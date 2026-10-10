"""Offline persistence regressions shared by SQLite and migrated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agents.contracts import (
    AgentOutput, AnalysisResult, EvidenceItem, QualificationResult, RunConfig, ScreeningResult, UsageInfo,
)
from app.agents.scoring import calculate_score_with_reason
from app.models import Analysis, AnalysisRun, ImportBatch, Message, Product, Usage, User
from app.schemas.api import ProductOut
from app.services import analysis_service as service
from test_postgres_failure_recovery import postgres_factory  # Reuse isolated migrated schemas.


@pytest.fixture(params=["factory", "postgres_factory"], ids=["sqlite", "postgresql"])
def persistence_factory(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def run_sources(persistence_factory):
    return seed_run(persistence_factory)


def seed_run(persistence_factory):
    with persistence_factory() as session:
        user = User(email=f"persistence-{uuid4()}@example.test", password_hash="unused-offline-fixture")
        session.add(user)
        session.flush()
        product = Product(user_id=user.id, name="Accounting QA", description="Invoices and expense tracking",
                          target_customer="Small businesses", problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        batch = ImportBatch(user_id=user.id, community_name="Offline QA", filename="three.csv",
                            checksum=uuid4().hex, row_count=3)
        session.add_all([product, batch])
        session.flush()
        messages = [Message(batch_id=batch.id, external_id=f"message-{index}", conversation_id="same",
                            author="QA", content=f"I need accounting software for invoices. Question {index}?",
                            normalized_content="accounting software", timestamp=datetime(2026, 10, 10, 9, index, tzinfo=timezone.utc))
                    for index in range(3)]
        session.add_all(messages)
        session.flush()
        run = AnalysisRun(user_id=user.id, product_id=product.id, batch_id=batch.id,
                          product_snapshot=ProductOut.model_validate(product).model_dump(mode="json", exclude={"created_at"}),
                          config_snapshot=RunConfig(provider_mode="real").model_dump(), idempotency_key=uuid4().hex,
                          total_count=3)
        session.add(run)
        session.commit()
        return {"run_id": run.id, "user_id": user.id, "message_ids": [m.id for m in messages]}


class OfflineAgent:
    """Structured provider-response fixture; never constructs a network provider."""
    def __init__(self, intent="searching_for_product", *, repair=False, cost=None):
        self.intent, self.repair, self.cost, self.calls = intent, repair, cost, []

    def __call__(self, inputs):
        self.calls.append(inputs.message.id)
        qualification = QualificationResult(intent=self.intent, need="Accounting software for invoices",
            purchase_intent=.85, product_fit=.90, need_strength=.80, urgency=.0, confidence=.90,
            response_opportunity=.85, evidence=[EvidenceItem(message_id=inputs.message.id,
                quote=inputs.message.content, reason="Exact supplied source")], limitations=["Price unknown"])
        scoring, reason = calculate_score_with_reason(qualification, valid_purchase_evidence=True)
        usage = [UsageInfo(stage="qualification", attempt_no=1, provider_mode="real", model="offline-provider-fixture",
            input_tokens=1289, output_tokens=329, estimated_cost=self.cost,
            cost_status="known" if self.cost is not None else "unknown", price_version="offline-fixture" if self.cost is not None else None,
            latency_ms=4, outcome="invalid_output" if self.repair else "success")]
        if self.repair:
            usage.append(usage[0].model_copy(update={"stage": "qualification_repair", "attempt_no": 2, "outcome": "success"}))
        return AgentOutput(screening=ScreeningResult(is_candidate=True, reason="offline fixture"),
            qualification=qualification, scoring=scoring, decision_reason=reason,
            prompt_version="qualify_real_v1", scoring_version="score_v1", usage=usage)


def rows(factory, run_id):
    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        analyses = session.scalars(select(Analysis).where(Analysis.run_id == run_id)).all()
        usage = session.scalars(select(Usage).where(Usage.run_id == run_id)).all()
        session.expunge_all()
        return run, {a.message_id: a for a in analyses}, usage


@pytest.mark.parametrize("intent", ["searching_for_product", "x" * 101, "نیاز به نرم‌افزار حسابداری " * 12, "🙂" * 130],
                         ids=["short", "long", "persian", "unicode"])
def test_intent_projection_preserves_complete_agent_output(persistence_factory, run_sources, intent):
    agent = OfflineAgent(intent)
    assert service.process_one(persistence_factory, agent_orchestrator=agent)
    run, analyses, usage = rows(persistence_factory, run_sources["run_id"])
    assert run.status == "completed" and run.failed_count == 0 and run.processed_count == 3
    assert len(analyses) == len(usage) == 3
    for analysis in analyses.values():
        assert analysis.intent == intent[:100]
        output = AgentOutput.model_validate(analysis.agent_output)
        assert output.qualification.intent == intent
        assert analysis.evidence == [item.model_dump(mode="json") for item in output.qualification.evidence]
        assert analysis.lead_score == output.scoring.score and analysis.decision == output.scoring.decision.value.lower()
        assert output.scoring == calculate_score_with_reason(output.qualification, True)[0]
    assert all(u.cost_usd is None and u.cost_status == "unknown" and u.input_tokens == 1289 and u.output_tokens == 329 for u in usage)


@pytest.mark.parametrize("failed_index", [0, 1, 2], ids=["first", "middle", "last"])
def test_poisoned_message_transaction_is_isolated_and_usage_survives(persistence_factory, run_sources, monkeypatch, failed_index):
    failed_id = run_sources["message_ids"][failed_index]
    original = service.persist_agent_output
    agent = OfflineAgent()
    def poison(session, **kwargs):
        if kwargs["target_message_id"] == failed_id:
            # Paid usage must already be durable BEFORE inserting the Analysis.
            with persistence_factory() as independent:
                paid = independent.scalar(select(Usage).where(Usage.run_id == run_sources["run_id"], Usage.message_id == failed_id))
                assert paid is not None and paid.outcome == "success" and paid.analysis_id is None
            original(session, **kwargs)
            # An actual NOT NULL violation poisons SQLAlchemy on both databases.
            session.add(Usage(run_id=kwargs["run_id"], stage=None, attempt_no=1, provider_mode="real", cost_status="unknown", outcome="success"))
            session.flush()
            pytest.fail("Database should reject the invalid usage row")
        return original(session, **kwargs)
    monkeypatch.setattr(service, "persist_agent_output", poison)
    assert service.process_one(persistence_factory, agent_orchestrator=agent)
    run, analyses, usage = rows(persistence_factory, run_sources["run_id"])
    assert run.status == "partial" and run.processed_count == 3 and run.failed_count == 1
    assert len(analyses) == 3 and len(usage) == 3 and len(agent.calls) == 3
    assert analyses[failed_id].status == "failed" and analyses[failed_id].failure_category == "internal_analysis_failure"
    assert analyses[failed_id].agent_output is None
    assert all(a.status == "completed" for mid, a in analyses.items() if mid != failed_id)
    assert all(u.outcome == "success" and u.cost_usd is None and u.cost_status == "unknown" for u in usage)
    assert all(u.analysis_id == analyses[u.message_id].id for u in usage)
    assert not service.process_one(persistence_factory, agent_orchestrator=agent)
    assert len(rows(persistence_factory, run_sources["run_id"])[2]) == 3


def test_retry_preserves_successes_and_counts_only_new_attempt(persistence_factory, run_sources, monkeypatch):
    failed_id = run_sources["message_ids"][1]
    original = service.persist_agent_output
    fail = True
    def poison(session, **kwargs):
        if fail and kwargs["target_message_id"] == failed_id:
            session.add(Usage(run_id=kwargs["run_id"], stage=None, attempt_no=1, provider_mode="real", cost_status="unknown", outcome="success"))
            session.flush()
        return original(session, **kwargs)
    monkeypatch.setattr(service, "persist_agent_output", poison)
    agent = OfflineAgent()
    assert service.process_one(persistence_factory, agent_orchestrator=agent)
    before, originals, usage = rows(persistence_factory, run_sources["run_id"])
    assert before.status == "partial" and len(usage) == 3
    with persistence_factory() as session:
        queued = service.retry_run(session, before.id, run_sources["user_id"], "explicit-offline-retry")
        assert queued.attempt_no == 2
        assert service.retry_run(session, before.id, run_sources["user_id"], "explicit-offline-retry").attempt_no == 2
    fail = False
    assert service.process_one(persistence_factory, agent_orchestrator=agent)
    after, analyses, usage = rows(persistence_factory, before.id)
    assert after.status == "completed" and after.processed_count == 3 and after.failed_count == 0
    assert agent.calls.count(failed_id) == 2 and len(agent.calls) == 4 and len(usage) == 4
    for mid, old in originals.items():
        assert analyses[mid].id == old.id
        if mid != failed_id: assert analyses[mid].agent_output == old.agent_output
    assert sorted(u.run_attempt_no for u in usage if u.message_id == failed_id) == [1, 2]


def test_usage_survives_even_when_failure_record_cannot_be_inserted(persistence_factory, run_sources, monkeypatch):
    def broken_analysis(session, **kwargs):
        # Neither successful nor failed Analysis insert can be committed.
        session.add(Analysis(run_id=kwargs["run_id"], message_id=kwargs.get("target_message_id", kwargs.get("message_id")), status=None))
        session.flush()
    monkeypatch.setattr(service, "persist_agent_output", broken_analysis)
    monkeypatch.setattr(service, "_persist_result", broken_analysis)
    with pytest.raises(IntegrityError):
        service.process_one(persistence_factory, agent_orchestrator=OfflineAgent())
    run, analyses, usage = rows(persistence_factory, run_sources["run_id"])
    assert not analyses and len(usage) == 1
    assert usage[0].analysis_id is None and usage[0].outcome == "success" and usage[0].input_tokens == 1289
    # It remains recoverable rather than falsely declaring completion.
    assert run.status == "running"


@pytest.mark.parametrize("cost", [None, Decimal("0.0006526")], ids=["unknown", "known-estimate"])
def test_attempt_usage_deduplicates_repair_and_preserves_cost(persistence_factory, run_sources, cost):
    agent = OfflineAgent(repair=True, cost=cost)
    assert service.process_one(persistence_factory, agent_orchestrator=agent)
    run, analyses, usage = rows(persistence_factory, run_sources["run_id"])
    assert run.status == "completed" and len(usage) == 6
    with persistence_factory() as session:
        for mid in run_sources["message_ids"]:
            events = AgentOutput.model_validate(analyses[mid].agent_output).usage
            service._save_late_usage(session, run.id, 1, mid, events)
            service._save_late_usage(session, run.id, 1, mid, events)
        session.commit()
    usage = rows(persistence_factory, run.id)[2]
    assert len(usage) == 6
    assert all(u.cost_usd == cost and u.cost_status == ("known" if cost is not None else "unknown") for u in usage)
    assert sum(u.outcome == "success" for u in usage) == 3
    assert sum(u.outcome == "invalid_output" for u in usage) == 3


def test_postgres_concurrent_late_usage_is_not_double_counted(postgres_factory):
    factory = postgres_factory
    sources = seed_run(factory)
    event = UsageInfo(stage="qualification", provider_mode="real", model="offline-fixture", input_tokens=2, output_tokens=1, outcome="success")
    def save():
        with factory() as session:
            service._save_late_usage(session, sources["run_id"], 1, sources["message_ids"][0], [event])
            session.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(save),pool.submit(save)]
        for task in futures: task.result(timeout=15)
    assert len(rows(factory, sources["run_id"])[2]) == 1


def test_legacy_result_projection_uses_same_database_limit(persistence_factory, run_sources):
    full_intent = "???? ?????? ???? " * 15
    result = AnalysisResult(status="completed", is_candidate=True, screening_reason="offline fixture",
                            intent=full_intent, decision="review", reason="Offline fixture", provider_mode="real")
    with persistence_factory() as session:
        row = service._persist_result(session, run_id=run_sources["run_id"], attempt=1,
            message_id=run_sources["message_ids"][0], result=result, usage=[])
        session.commit()
        assert row.intent == full_intent[:100]
