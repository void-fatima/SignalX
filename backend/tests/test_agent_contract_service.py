import json

import httpx
from sqlalchemy import select
import pytest

from app.agents.contracts import (
    AgentInput, AgentOutput, EvidenceItem, QualificationResult, RunConfig,
    ScoringResult, ScreeningResult, UsageInfo,
)
from app.agents.orchestrator import analyze_agent
from app.agents.providers.factory import real_provider_client
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
        assert all(analysis.decision_reason
                   and analysis.scoring_version == "score_v1"
                   and analysis.prompt_version is None
                   for analysis in analyses if analysis.is_candidate)
        assert all(analysis.decision_reason and analysis.scoring_version is None
                   and analysis.prompt_version is None
                   for analysis in analyses if not analysis.is_candidate)
        assert any(event.model is None or event.model == "deterministic-mock-v1" for event in usage)
        assert any(event.cost_status == "mock" and event.cost_usd == 0 for event in usage)


def test_worker_persists_real_output_and_keeps_unknown_cost_null(client, factory):
    payload, run = setup_run(client, key="real-agent-contract-worker")
    with factory() as session:
        analysis_run = session.get(AnalysisRun, run["id"])
        analysis_run.config_snapshot = {**analysis_run.config_snapshot, "provider_mode": "real"}
        session.commit()

    def real_contract_fixture(agent_input):
        message = agent_input.message
        qualification = QualificationResult(
            intent="course_search", need="Looking for a backend course", purchase_intent=.8,
            product_fit=.8, need_strength=.7, urgency=.4, confidence=.9, response_opportunity=.8,
            evidence=[EvidenceItem(message_id=message.id, quote=message.content, reason="Contract test evidence")],
            limitations=["Budget is unknown"],
        )
        return AgentOutput(
            screening=ScreeningResult(is_candidate=True, reason="direct_signal"),
            qualification=qualification,
            scoring=ScoringResult(score=72, decision="RESPOND"),
            decision_reason="The score meets the respond threshold.",
            prompt_version="qualify_real_v1", scoring_version="score_v1",
            usage=[UsageInfo(stage="qualification", attempt_no=1, provider_mode="real",
                model="contract-test-model", input_tokens=120, output_tokens=30,
                estimated_cost=None, cost_status="unknown", price_version=None,
                latency_ms=12, outcome="success")],
        )

    assert process_one(factory, agent_orchestrator=real_contract_fixture)
    status = client.get(f"/api/v1/analysis/runs/{run['id']}")
    assert status.status_code == 200 and status.json()["status"] == "completed"
    with factory() as session:
        analyses = session.scalars(select(Analysis).where(Analysis.run_id == run["id"])).all()
        usage_rows = session.scalars(select(Usage).where(Usage.run_id == run["id"])).all()
        assert len(analyses) == len(usage_rows) == 20
        assert all(row.provider_mode == "real" and row.decision_reason
                   and row.scoring_version == "score_v1"
                   and row.prompt_version == "qualify_real_v1" for row in analyses)
        assert all(row.provider_mode == "real" and row.cost_usd is None
                   and row.cost_status == "unknown" for row in usage_rows)

    detail = client.get(f"/api/v1/leads/{analyses[0].id}")
    assert detail.status_code == 200
    assert detail.json()["analysis"]["provider_mode"] == "real"
    assert detail.json()["analysis"]["decision_reason"]
    assert detail.json()["analysis"]["prompt_version"] == "qualify_real_v1"


def test_worker_gemini_orchestrator_persists_agent_output_and_usage(client, factory, monkeypatch):
    """Exercise the Gemini adapter through the production Worker boundary without network calls."""
    _payload, run = setup_run(client, key="gemini-agent-contract-worker")
    with factory() as session:
        analysis_run = session.get(AnalysisRun, run["id"])
        analysis_run.config_snapshot = {**analysis_run.config_snapshot, "provider_mode": "real"}
        session.commit()

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-worker-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    requests = []

    def handle(request):
        requests.append(request)
        request_body = json.loads(request.content)
        supplied = json.loads(request_body["messages"][-1]["content"])
        target = supplied["target"]
        qualification = {
            "intent": "course_search",
            "need": "Looking for a beginner backend course",
            "purchase_intent": 0.9,
            "product_fit": 0.9,
            "need_strength": 0.8,
            "urgency": 0.4,
            "confidence": 0.9,
            "response_opportunity": 0.8,
            "evidence": [{
                "message_id": target["id"],
                "quote": target["content"],
                "reason": "The target message is the supplied evidence.",
            }],
            "limitations": ["Budget is unknown"],
        }
        response = {
            "model": "gemini-3.5-flash-lite",
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(qualification)},
            }],
            "usage": {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165},
        }
        return httpx.Response(200, json=response)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client_transport:
        with real_provider_client(client_transport):
            assert process_one(factory, agent_orchestrator=analyze_agent)

    with factory() as session:
        analyses = session.scalars(select(Analysis).where(Analysis.run_id == run["id"])).all()
        usage_rows = session.scalars(select(Usage).where(Usage.run_id == run["id"])).all()
        run_record = session.get(AnalysisRun, run["id"])

    assert run_record.status == "completed"
    assert run_record.processed_count == len(analyses) == 20
    candidate_rows = [row for row in analyses if row.is_candidate]
    assert candidate_rows and len(requests) == len(usage_rows) == len(candidate_rows)
    assert all(row.provider_mode == "real" for row in analyses)
    assert all(row.agent_output is not None for row in analyses)
    assert all(row.prompt_version == "qualify_gemini_v1" for row in candidate_rows)
    assert all(row.scoring_version == "score_v1" and row.decision_reason for row in candidate_rows)
    assert all(row.agent_output["scoring"]["score"] == row.lead_score for row in candidate_rows)
    assert all(event.provider_mode == "real" and event.model == "gemini-3.5-flash-lite"
               and event.input_tokens == 120 and event.output_tokens == 45
               and event.cost_usd is None and event.cost_status == "unknown"
               for event in usage_rows)

    response = client.get(f"/api/v1/leads?run_id={run['id']}&decision=respond")
    assert response.status_code == 200
    assert response.json()["total"] > 0
    lead_id = response.json()["items"][0]["id"]
    detail = client.get(f"/api/v1/leads/{lead_id}")
    assert detail.status_code == 200
    assert detail.json()["analysis"]["provider_mode"] == "real"
    assert detail.json()["analysis"]["prompt_version"] == "qualify_gemini_v1"


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
