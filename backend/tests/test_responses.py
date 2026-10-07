import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agents.contracts import UsageInfo
from app.agents.orchestrator import analyze_agent
from app.agents.providers.base import ProviderError
from app.main import app
from app.models import Analysis, LeadFeedback, SuggestedResponse, Usage
from app.schemas.api import LeadDetail
from app.services.analysis_service import process_one
from test_flow import setup_run


def analyzed_run(client, factory, *, key=None):
    _, run = setup_run(client, key=key or f"responses-{uuid4()}")
    assert process_one(factory, agent_orchestrator=analyze_agent)
    leads = client.get(f"/api/v1/leads?run_id={run['id']}&decision=respond").json()
    assert leads["total"] > 0
    return run, leads["items"][0]["id"]


def test_shared_lead_fixture_matches_extended_detail_contract():
    fixture = Path(__file__).resolve().parents[2] / "contracts" / "examples" / "lead.json"
    LeadDetail.model_validate(json.loads(fixture.read_text(encoding="utf-8")))


def test_response_is_generated_once_edited_approved_and_regenerated_explicitly(client, factory):
    run, analysis_id = analyzed_run(client, factory)

    first = client.post(f"/api/v1/leads/{analysis_id}/response")
    assert first.status_code == 200, first.text
    draft = first.json()
    assert draft["status"] == "pending" and draft["provider_mode"] == "mock"
    assert draft["response_text"]

    reused = client.post(f"/api/v1/leads/{analysis_id}/response")
    assert reused.json() == draft
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Usage).where(
            Usage.analysis_id == analysis_id, Usage.stage == "suggested_reply")) == 1

    detail = client.get(f"/api/v1/leads/{analysis_id}").json()
    assert detail["response_draft"]["response_text"] == draft["response_text"]
    assert detail["feedback"] is None
    assert client.patch(f"/api/v1/leads/{analysis_id}/response", json={"status": "edited"}).status_code == 422
    assert client.patch(f"/api/v1/leads/{analysis_id}/response", json={"response_text": "   "}).status_code == 422

    edited = client.patch(f"/api/v1/leads/{analysis_id}/response", json={
        "response_text": "What would you like to learn?",
    })
    assert edited.status_code == 200
    assert edited.json()["status"] == "edited"
    assert edited.json()["response_text"] == "What would you like to learn?"

    approved = client.patch(f"/api/v1/leads/{analysis_id}/response", json={"status": "approved"})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    regenerated = client.post(f"/api/v1/leads/{analysis_id}/response?regenerate=true")
    assert regenerated.status_code == 200
    assert regenerated.json()["status"] == "pending"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SuggestedResponse).where(
            SuggestedResponse.analysis_id == analysis_id)) == 1
        assert session.scalar(select(func.count()).select_from(Usage).where(
            Usage.run_id == run["id"], Usage.analysis_id == analysis_id,
            Usage.stage == "suggested_reply")) == 2
        stored = session.get(Analysis, analysis_id)
        assert stored.agent_output["suggested_reply"] == regenerated.json()["response_text"]
        assert len(stored.agent_output["usage"]) >= 2


def test_response_and_feedback_reject_ineligible_and_foreign_leads(client, factory):
    run, _ = analyzed_run(client, factory)
    ignored = client.get(f"/api/v1/leads?run_id={run['id']}&decision=ignore").json()["items"][0]
    assert client.post(f"/api/v1/leads/{ignored['id']}/response").status_code == 409

    with TestClient(app) as second:
        credentials = {"email": "other-response@example.test", "password": "correct horse battery"}
        assert second.post("/api/v1/auth/register", json=credentials).status_code == 201
        assert second.post("/api/v1/auth/login", json=credentials).status_code == 200
        assert second.post(f"/api/v1/leads/{ignored['id']}/response").status_code == 404
        assert second.put(f"/api/v1/leads/{ignored['id']}/feedback", json={"relevant": True}).status_code == 404


def test_failed_reply_attempt_keeps_unknown_usage_and_does_not_create_draft(client, factory, monkeypatch):
    _, analysis_id = analyzed_run(client, factory)

    def fail_with_usage(agent_input, analysis):
        raise ProviderError("synthetic timeout", [
            *analysis.usage,
            UsageInfo(stage="suggested_reply", attempt_no=1, provider_mode="mock", model="mock",
                      estimated_cost=None, cost_status="unknown", price_version=None,
                      latency_ms=25, outcome="timeout"),
        ])

    monkeypatch.setattr("app.services.response_service.generate_suggested_reply", fail_with_usage)
    response = client.post(f"/api/v1/leads/{analysis_id}/response")
    assert response.status_code == 502
    with factory() as session:
        assert session.scalar(select(SuggestedResponse).where(
            SuggestedResponse.analysis_id == analysis_id)) is None
        attempt = session.scalar(select(Usage).where(
            Usage.analysis_id == analysis_id, Usage.stage == "suggested_reply"))
        assert attempt is not None
        assert attempt.outcome == "timeout" and attempt.cost_status == "unknown"
        assert attempt.cost_usd is None
        stored = session.get(Analysis, analysis_id)
        assert stored.agent_output["usage"][-1]["outcome"] == "timeout"


def test_feedback_upserts_one_current_vote_per_analysis(client, factory):
    _, analysis_id = analyzed_run(client, factory)
    positive = client.put(f"/api/v1/leads/{analysis_id}/feedback", json={
        "relevant": True, "comment": "Reviewed",
    })
    assert positive.status_code == 200 and positive.json()["relevant"] is True
    negative = client.put(f"/api/v1/leads/{analysis_id}/feedback", json={
        "relevant": False, "comment": "Not a fit",
    })
    assert negative.status_code == 200 and negative.json()["relevant"] is False

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(LeadFeedback).where(
            LeadFeedback.analysis_id == analysis_id)) == 1
    detail = client.get(f"/api/v1/leads/{analysis_id}").json()
    assert detail["feedback"]["relevant"] is False
    assert detail["feedback"]["comment"] == "Not a fit"
