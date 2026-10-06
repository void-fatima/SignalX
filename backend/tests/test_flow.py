from datetime import timedelta
from pathlib import Path
from sqlalchemy import select, func
from app.models import Message, AnalysisRun, Analysis, Usage, utcnow
from app.services.analysis_service import process_one, recover_interrupted
from app.agents.providers.mock import MockProvider
from app.agents.providers.base import ProviderError
from app.agents.contracts import UsageEvent
from fastapi.testclient import TestClient
from app.main import app

DATA = Path(__file__).resolve().parents[2] / "data" / "demo_messages.csv"
PRODUCT = {"name": "Backend course", "description": "دوره بک‌اند پروژه‌محور", "target_customer": "Developers"}


def setup_run(client, key="test-run"):
    product = client.post("/api/v1/products", json=PRODUCT)
    assert product.status_code == 201
    batch = client.post("/api/v1/imports", data={"community_name": "demo"}, files={"file": ("demo.csv", DATA.read_bytes(), "text/csv")})
    assert batch.status_code == 201
    payload = {"product_id": product.json()["id"], "batch_id": batch.json()["batch"]["id"]}
    run = client.post("/api/v1/analysis/runs", json=payload, headers={"Idempotency-Key": key})
    assert run.status_code == 202
    return payload, run.json()


def test_end_to_end_dedup_and_snapshots(client, factory):
    payload, run = setup_run(client)
    duplicate = client.post("/api/v1/analysis/runs", json=payload, headers={"Idempotency-Key": "test-run"})
    assert duplicate.json()["id"] == run["id"]
    changed = client.post("/api/v1/products", json={**PRODUCT, "name": "Other"}).json()
    assert client.post("/api/v1/analysis/runs", json={**payload, "product_id": changed["id"]}, headers={"Idempotency-Key": "test-run"}).status_code == 409
    again = client.post("/api/v1/imports", data={"community_name": "demo"}, files={"file": ("renamed.csv", DATA.read_bytes())})
    assert again.json()["duplicate"] and again.json()["batch"]["id"] == payload["batch_id"]
    assert client.patch(f"/api/v1/products/{payload['product_id']}", json={"name": "Changed profile"}).status_code == 200
    assert process_one(factory)
    status = client.get(f"/api/v1/analysis/runs/{run['id']}").json()
    assert status["status"] == "completed" and status["processed_count"] == 20 and status["failed_count"] == 0
    assert status["finished_at"].endswith("Z")
    results = client.get(f"/api/v1/leads?run_id={run['id']}&decision=respond").json()
    assert results["total"] > 0
    detail = client.get(f"/api/v1/leads/{results['items'][0]['id']}").json()
    assert detail["product_snapshot"]["name"] == PRODUCT["name"]
    assert all(m["conversation_id"] == detail["message"]["conversation_id"] for m in detail["context"])
    assert detail["message"]["timestamp"].endswith("Z")
    ignored = client.get(f"/api/v1/leads?run_id={run['id']}&decision=ignore").json()["items"]
    assert any(a["lead_score"] is None and a["signals"] is None for a in ignored)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 20
        usage = session.scalars(select(Usage)).all()
        assert usage and all(u.cost_status == "mock" and u.cost_usd == 0 and u.input_tokens is None for u in usage)
    assert not process_one(factory)


def test_atomic_invalid_csv(client, factory):
    content = "external_id,conversation_id,author,content,timestamp\n1,a,test,valid,2026-10-04T08:00:00Z\n2,a,test,invalid,2026-10-04T08:00:00\n"
    response = client.post("/api/v1/imports", data={"community_name": "broken"}, files={"file": ("bad.csv", content)})
    assert response.status_code == 422 and response.json()["error"]["details"][0]["row"] == 3
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 0
    missing = client.get("/api/v1/products/not-a-uuid")
    assert missing.status_code == 422 and "error" in missing.json()


def test_partial_failure_and_attempt_usage(client, factory):
    _, run = setup_run(client)
    class FailingProvider(MockProvider):
        def qualify(self, product, target, context):
            if target.external_id == "m03":
                raise ProviderError("Synthetic failure", [UsageEvent(outcome="error")])
            return super().qualify(product, target, context)
    assert process_one(factory, FailingProvider())
    status = client.get(f"/api/v1/analysis/runs/{run['id']}").json()
    assert status["status"] == "partial" and status["failed_count"] == 1 and status["processed_count"] == 20
    with factory() as session:
        failed = session.scalar(select(Analysis).where(Analysis.status == "failed"))
        assert failed.decision is None and failed.lead_score is None
        assert session.scalar(select(Usage).where(Usage.outcome == "error")) is not None


def test_real_contract_failure_keeps_real_provider_mode(client, factory):
    _, run = setup_run(client, key="real-contract-failure")
    with factory() as session:
        current = session.get(AnalysisRun, run["id"])
        current.config_snapshot = {**current.config_snapshot, "provider_mode": "real"}
        session.commit()

    def fail_agent(_inputs):
        raise RuntimeError("Synthetic real-provider failure")

    assert process_one(factory, agent_orchestrator=fail_agent)
    with factory() as session:
        failed = session.scalar(select(Analysis).where(
            Analysis.run_id == run["id"], Analysis.status == "failed"))
        assert failed is not None
        assert failed.provider_mode == "real"


def test_expired_worker_recovery(client, factory):
    _, run = setup_run(client)
    with factory() as session:
        current = session.get(AnalysisRun, run["id"])
        current.status = "running"
        current.heartbeat_at = utcnow() - timedelta(minutes=10)
        session.commit()
    recover_interrupted(factory)
    assert client.get(f"/api/v1/analysis/runs/{run['id']}").json()["status"] == "interrupted"
    assert not process_one(factory)


def test_bom_and_cross_conversation_parent(client, factory):
    product = client.post("/api/v1/products", json=PRODUCT).json()
    csv = "external_id,conversation_id,author,content,timestamp,reply_to_external_id\n1,a,ali,دنبال دوره بک‌اند هستم,2026-10-04T08:00:00+03:30,\n2,b,mina,آره ولی گرونه,2026-10-04T08:01:00+03:30,1\n"
    imported = client.post("/api/v1/imports", data={"community_name": "BOM"}, files={"file": ("bom.csv", csv.encode("utf-8-sig"))}).json()
    assert len(imported["warnings"]) == 1
    run = client.post("/api/v1/analysis/runs", json={"product_id": product["id"], "batch_id": imported["batch"]["id"]}, headers={"Idempotency-Key": "BOM-run"}).json()
    process_one(factory)
    with factory() as session:
        target = session.scalar(select(Message).where(Message.external_id == "2"))
        analysis = session.scalar(select(Analysis).where(Analysis.message_id == target.id))
        assert analysis.run_id == run["id"] and analysis.context_message_ids == []
        assert analysis.lead_score < 70


def test_duplicate_row_is_rejected(client, factory):
    csv = "external_id,conversation_id,author,content,timestamp\n1,a,test,one,2026-10-04T08:00:00Z\n1,a,test,two,2026-10-04T08:01:00Z\n"
    response = client.post("/api/v1/imports", data={"community_name": "duplicate"}, files={"file": ("duplicate.csv", csv)})
    assert response.status_code == 422
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 0


def test_user_data_isolation_and_per_user_deduplication(client, factory):
    first_payload, first_run = setup_run(client, key="same-key")
    first_product_id = first_payload["product_id"]

    with TestClient(app) as second:
        credentials = {"email": "second@example.test", "password": "correct horse battery"}
        assert second.post("/api/v1/auth/register", json=credentials).status_code == 201
        assert second.post("/api/v1/auth/login", json=credentials).status_code == 200
        assert second.get("/api/v1/products").json()["total"] == 0
        assert second.get(f"/api/v1/products/{first_product_id}").status_code == 404
        assert second.get(f"/api/v1/messages?batch_id={first_payload['batch_id']}").status_code == 404
        assert second.get(f"/api/v1/analysis/runs/{first_run['id']}").status_code == 404
        assert second.get(f"/api/v1/leads?run_id={first_run['id']}").status_code == 404

        product = second.post("/api/v1/products", json=PRODUCT)
        assert product.status_code == 201
        batch = second.post("/api/v1/imports", data={"community_name": "demo"},
            files={"file": ("demo.csv", DATA.read_bytes(), "text/csv")})
        assert batch.status_code == 201 and batch.json()["duplicate"] is False
        payload = {"product_id": product.json()["id"], "batch_id": batch.json()["batch"]["id"]}
        cross_user_run = {"product_id": product.json()["id"], "batch_id": first_payload["batch_id"]}
        assert second.post("/api/v1/analysis/runs", json=cross_user_run,
            headers={"Idempotency-Key": "cross-user"}).status_code == 404
        run = second.post("/api/v1/analysis/runs", json=payload, headers={"Idempotency-Key": "same-key"})
        assert run.status_code == 202
        assert run.json()["id"] != first_run["id"]


def test_api_rejects_requests_without_a_session(app_client):
    assert app_client.get("/api/v1/products").status_code == 401
    assert app_client.post("/api/v1/products", json=PRODUCT).status_code == 401
