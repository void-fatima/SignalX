from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agents.orchestrator import analyze_agent
from app.main import app
from app.models import Analysis, AnalysisRun, LeadFeedback, Usage
from app.services.analysis_service import process_one
from test_flow import setup_run


def analyzed_run(client, factory):
    _, run = setup_run(client, key=f"analytics-{uuid4()}")
    assert process_one(factory, agent_orchestrator=analyze_agent)
    leads = client.get(f"/api/v1/leads?run_id={run['id']}&decision=respond").json()
    assert leads["total"] > 0
    return run, leads["items"][0]["id"]


def test_run_analytics_preserves_partial_known_cost_and_unknown_usage(client, factory):
    run, analysis_id = analyzed_run(client, factory)
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
        run_row = session.get(AnalysisRun, run["id"])
        run_row.config_snapshot = {**run_row.config_snapshot, "provider_mode": "real"}
        failed = session.scalar(select(Analysis).where(
            Analysis.run_id == run["id"], Analysis.id != analysis_id).limit(1))
        assert failed is not None
        failed.status = "failed"
        failed.decision = "respond"
        run_row.failed_count = 1
        usage_rows = session.scalars(select(Usage).where(Usage.run_id == run["id"])).all()
        assert usage_rows
        for row in usage_rows:
            row.provider_mode = "real"
            row.cost_status = "known"
            row.cost_usd = Decimal("0.01")
        session.add(Usage(
            run_id=run["id"], analysis_id=analysis_id,
            message_id=session.get(Analysis, analysis_id).message_id,
            stage="suggested_reply", attempt_no=1, provider_mode="real", model="model-x",
            input_tokens=None, output_tokens=None, cost_usd=None, cost_status="unknown",
            price_version=None, latency_ms=None, outcome="timeout",
        ))
        session.add(Usage(
            run_id=run["id"], analysis_id=analysis_id,
            message_id=session.get(Analysis, analysis_id).message_id,
            stage="qualification", attempt_no=99, provider_mode="mock", model="mock",
            input_tokens=None, output_tokens=None, cost_usd=Decimal("0"), cost_status="mock",
            price_version="mock_v1", latency_ms=0, outcome="success",
        ))
        session.commit()

    report = client.get(f"/api/v1/analytics/overview?run_id={run['id']}")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["provider_mode"] == "real"
    assert body["total_count"] == 20 and body["qualified_leads"] == 4
    assert body["failed_count"] == 1
    assert body["unknown_usage_count"] == 2 and body["cost_complete"] is False
    assert Decimal(body["total_cost_usd"]) > 0  # recorded subtotal, explicitly incomplete
    assert body["cost_per_message"] is None and body["cost_per_qualified_lead"] is None
    assert body["feedback_acceptance"] == 0
    assert body["feedback_coverage"] is not None and 0 < body["feedback_coverage"] <= 1


def test_analytics_is_user_scoped(client, factory):
    _, run = setup_run(client, key=f"analytics-scope-{uuid4()}")
    with TestClient(app) as second:
        credentials = {"email": "other-analytics@example.test", "password": "correct horse battery"}
        assert second.post("/api/v1/auth/register", json=credentials).status_code == 201
        assert second.post("/api/v1/auth/login", json=credentials).status_code == 200
        response = second.get(f"/api/v1/analytics/overview?run_id={run['id']}")
    assert response.status_code == 404


def test_analytics_nulls_rates_with_zero_denominators(client, factory):
    _, run = setup_run(client, key=f"analytics-empty-{uuid4()}")
    with factory() as session:
        row = session.get(AnalysisRun, run["id"])
        row.total_count = 0
        session.commit()
    report = client.get(f"/api/v1/analytics/overview?run_id={run['id']}")
    assert report.status_code == 200
    body = report.json()
    assert body["cost_per_message"] is None
    assert body["cost_per_qualified_lead"] is None
    assert body["feedback_acceptance"] is None
    assert body["feedback_coverage"] is None
