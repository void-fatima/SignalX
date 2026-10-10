"""Dedicated test database and unique schema: production/local app data is untouched."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.models import User, Product
from app.discovery.models import DiscoverySearch, DiscoveryBudget
from app.discovery.schemas import SearchInput, DiscoveryResult
from app.discovery.service import perform_search
from app.discovery import service
from test_postgres_failure_recovery import postgres_factory


def test_postgres_concurrent_idempotent_search_reserves_one_request(postgres_factory,monkeypatch):
    factory=postgres_factory
    with factory() as session:
        user=User(email=f"discovery-{uuid4()}@example.test",password_hash="unused-test-hash")
        session.add(user);session.flush()
        product=Product(user_id=user.id,name="LedgerFlow",description="Accounting",target_customer="Finance teams",problems_solved=[],best_fit=[],not_fit=[],currency="USD")
        session.add(product);session.commit();owner=user.id;product_id=product.id
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY","offline-source-key")
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    entered,release=Event(),Event();calls=[]
    class Adapter:
        def search(self,inputs):
            calls.append(inputs);entered.set();assert release.wait(15)
            return [DiscoveryResult(source="brave",source_id="one",title="Finance",url="https://company.example.com/",excerpt="Finance tools")]
    monkeypatch.setattr(service,"get_discovery_provider",lambda source:Adapter())
    inputs=SearchInput(product_id=product_id,source="brave",keywords="finance")
    def run():
        with factory() as session: return perform_search(session,owner,inputs,"same-key")
    with ThreadPoolExecutor(max_workers=1) as pool:
        task=pool.submit(run)
        try:
            assert entered.wait(15)
            replay=run();assert replay.status=="pending" and replay.request_count==0
        finally: release.set()
        result=task.result(timeout=15)
    assert result.status=="completed" and len(calls)==1
    with factory() as session:
        assert len(session.scalars(select(DiscoverySearch)).all())==1
        assert session.get(DiscoveryBudget,"brave").request_count==1


def test_postgres_additive_tables_keep_existing_product(postgres_factory):
    factory=postgres_factory
    with factory() as session:
        product=Product(name="Retained profile",description="Existing description",target_customer="Owners",problems_solved=[],best_fit=[],not_fit=[],currency="USD")
        session.add(product);session.commit();id=product.id
    with factory() as session:
        assert session.get(Product,id).description=="Existing description"
        assert session.scalars(select(DiscoverySearch)).all()==[]


def test_postgres_concurrent_cache_receipts_replay_after_expiry(postgres_factory,monkeypatch):
    from datetime import timedelta
    from app.models import utcnow
    factory=postgres_factory
    with factory() as session:
        user=User(email=f"cache-{uuid4()}@example.test",password_hash="unused-test-hash")
        session.add(user); session.flush()
        product=Product(user_id=user.id,name="Profile",description="Finance",target_customer="Teams",
            problems_solved=[],best_fit=[],not_fit=[],currency="USD")
        session.add(product);session.commit();owner=user.id;product_id=product.id
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY","offline-source-key")
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    calls=[];now=utcnow();monkeypatch.setattr(service,"utcnow",lambda:now)
    class Adapter:
        def search(self,inputs):
            calls.append(inputs)
            return [DiscoveryResult(source="brave",source_id="one",title="Finance",url="https://company.example.com/",excerpt="Tools")]
    monkeypatch.setattr(service,"get_discovery_provider",lambda source:Adapter())
    inputs=SearchInput(product_id=product_id,source="brave",keywords="finance")
    def run(key):
        with factory() as session:return perform_search(session,owner,inputs,key)
    first=run("first")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,["cached","cached"]))
    assert all(result.id==first.id for result in results)
    now+=timedelta(minutes=16)
    assert run("cached").id==first.id and len(calls)==1
    with factory() as session:
        assert len(session.scalars(select(DiscoverySearch)).all())==2
        assert session.get(DiscoveryBudget,"brave").request_count==1


def test_postgres_forward_0007_to_0009_preserves_existing_data(postgres_factory):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from sqlalchemy import inspect, text
    from app.models import Analysis, AnalysisRun, ImportBatch, Message, utcnow

    factory = postgres_factory
    with factory() as session:
        engine = session.get_bind()
    env = {**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False)}
    root = Path(__file__).resolve().parents[1]
    def migrate(*args):
        result = subprocess.run([sys.executable, "-m", "alembic", *args],
            cwd=root, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    # This fixture owns a unique schema in an isolated test database only.
    migrate("downgrade", "0007")
    with factory() as session:
        user = User(email=f"migration-{uuid4()}@example.test", password_hash="unused-test-hash")
        session.add(user); session.flush()
        product = Product(user_id=user.id, name="Existing business", description="Retain me",
            target_customer="Teams", problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        batch = ImportBatch(user_id=user.id, community_name="Existing", filename="synthetic.csv",
            checksum=uuid4().hex, row_count=1)
        session.add_all([product, batch]); session.flush()
        message = Message(batch_id=batch.id, external_id="existing", conversation_id="thread",
            author="QA", content="Existing source", normalized_content="existing source", timestamp=utcnow())
        run = AnalysisRun(user_id=user.id, product_id=product.id, batch_id=batch.id,
            product_snapshot={}, config_snapshot={}, idempotency_key=uuid4().hex, total_count=1,
            status="completed", processed_count=1)
        session.add_all([message, run]); session.flush()
        analysis = Analysis(run_id=run.id, message_id=message.id, status="completed",
            is_candidate=True, screening_reason="Existing", reason="Preserve result", provider_mode="real",
            agent_output={"retained": True})
        session.add(analysis); session.commit()
        ids = user.id, product.id, analysis.id
    migrate("upgrade", "head")
    with factory() as session:
        assert session.get(User, ids[0]).email.startswith("migration-")
        assert session.get(Product, ids[1]).description == "Retain me"
        assert session.get(Analysis, ids[2]).agent_output == {"retained": True}
        assert session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0009"
        assert {"discovery_searches", "discovery_prospects", "discovery_budgets"} <= set(inspect(engine).get_table_names())
        assert {"operation_token", "operation_started_at"} <= {c["name"] for c in inspect(engine).get_columns("telegram_deliveries")}
