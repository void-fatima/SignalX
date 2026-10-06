from sqlalchemy import select
import pytest

from app.agents.contracts import (
    AgentInput, AgentOutput, EvidenceItem, QualificationResult, RunConfig,
    ScoringResult, ScreeningResult,
)
from app.agents.orchestrator import analyze_agent
from app.models import Analysis, AnalysisRun, Usage
from app.services.agent_contract_service import build_agent_input, validate_agent_output
from app.services.analysis_service import process_one
from app.services.context_service import load_messages
from test_flow import PRODUCT, setup_run


def test_backend_builds_agent_input_with_internal_parent_and_scoped_context(client, factory):
    payload, run = setup_run(client, key="agent-contract-input")
    with factory() as session:
        analysis_run = session.get(AnalysisRun, run["id"])
        messages = load_messages(session, payload["batch_id"])
        target = next(message for message in messages if message.external_id == "m04")
        agent_input = build_agent_input(
            product_snapshot={**analysis_run.product_snapshot, "id": analysis_run.product_id},
            run_id=analysis_run.id,
            provider_mode=analysis_run.config_snapshot["provider_mode"],
            target=target,
            messages=messages,
            config=RunConfig.model_validate(analysis_run.config_snapshot),
        )

    assert agent_input.product.name == PRODUCT["name"]
    assert agent_input.message.id == target.id
    expected_parent = next(message for message in messages if message.external_id == "m03")
    assert agent_input.message.reply_to_message_id == expected_parent.id
    assert agent_input.message.reply_to_message_id != target.reply_to_external_id
    assert expected_parent.id in {item.id for item in agent_input.context_messages}
    assert all(item.id != agent_input.message.id for item in agent_input.context_messages)
    assert len(agent_input.context_messages) <= 5
    assert agent_input.metadata.run_id == run["id"]
    assert agent_input.metadata.provider_mode == "mock"


def test_worker_contract_path_persists_complete_agent_output(client, factory):
    _payload, run = setup_run(client, key="agent-contract-worker")
    assert process_one(factory, agent_orchestrator=analyze_agent)

    with factory() as session:
        analyses = session.scalars(select(Analysis).where(Analysis.run_id == run["id"])).all()
        usage = session.scalars(select(Usage).where(Usage.run_id == run["id"])).all()
        run_record = session.get(AnalysisRun, run["id"])
        assert run_record.status == "completed"
        assert run_record.processed_count == len(analyses) == 20
        assert usage
        assert all(analysis.agent_output is not None for analysis in analyses)
        assert any(analysis.agent_output["scoring"]["score"] == analysis.lead_score
                   for analysis in analyses if analysis.lead_score is not None)
        assert all(analysis.reason == analysis.need and analysis.budget_signal == "unknown"
                   for analysis in analyses if analysis.is_candidate)
        assert any(event.model is None or event.model == "deterministic-mock-v1" for event in usage)
        assert any(event.cost_status == "mock" and event.cost_usd == 0 for event in usage)


def test_backend_rejects_agent_evidence_outside_input():
    inputs = AgentInput.model_validate({
        "product": {"id": "p1", "name": "Course", "description": "Backend course", "target_customer": "Developers"},
        "message": {"id": "m1", "content": "Looking for a backend course", "author": "user",
                    "timestamp": "2026-10-05T12:00:00Z", "conversation_id": "c1"},
        "metadata": {"run_id": "r1", "provider_mode": "mock"},
    })
    qualification = QualificationResult(
        intent="course_search", need="backend course", purchase_intent=.9,
        product_fit=.9, need_strength=.8, urgency=.5, confidence=.9,
        response_opportunity=.8,
        evidence=[EvidenceItem(message_id="foreign", quote="unseen content", reason="untrusted")],
    )
    output = AgentOutput(
        screening=ScreeningResult(is_candidate=True, reason="direct_signal"),
        qualification=qualification,
        scoring=ScoringResult(score=80, decision="RESPOND"),
    )
    with pytest.raises(ValueError, match="outside AgentInput"):
        validate_agent_output(inputs, output)
