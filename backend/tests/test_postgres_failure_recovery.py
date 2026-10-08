"""PostgreSQL migration and worker-fencing checks; set TEST_POSTGRES_URL to an isolated test DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.agents.contracts import RunConfig
from app.agents.providers.mock import MockProvider
from app.models import Analysis, AnalysisRun, ImportBatch, Message, Product, Usage, User, utcnow
from app.schemas.api import ProductOut
from app.services.analysis_service import process_one, recover_interrupted, retry_run


BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def postgres_factory():
    raw_url = os.environ.get("TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("TEST_POSTGRES_URL is not configured")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("TEST_POSTGRES_URL must use PostgreSQL")
    if "test" not in (url.database or "").lower():
        pytest.fail("TEST_POSTGRES_URL must point to an isolated database whose name contains 'test'")

    admin = create_engine(url, pool_pre_ping=True)
    schema = "sx_test_" + uuid4().hex
    scoped_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = None
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        env = {**os.environ, "DATABASE_URL": scoped_url.render_as_string(hide_password=False)}
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_ROOT, env=env, text=True, capture_output=True,
        )
        assert migration.returncode == 0, migration.stdout + migration.stderr
        engine = create_engine(scoped_url, pool_pre_ping=True)
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_migrated_worker_claim_and_stale_retry_fencing(postgres_factory):
    factory = postgres_factory
    with factory() as session:
        user = User(email=f"pg-{uuid4()}@example.test", password_hash="unused-test-hash")
        product = Product(user_id=None, name="Python course", description="Beginner projects",
            target_customer="Python beginners", problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        session.add_all([user, product])
        session.flush()
        product.user_id = user.id
        batch = ImportBatch(user_id=user.id, community_name=f"pg-{uuid4()}", filename="one.csv",
            checksum=uuid4().hex, row_count=1)
        session.add(batch)
        session.flush()
        message = Message(batch_id=batch.id, external_id="one", conversation_id="same-conversation",
            author="customer", content="I want to buy a beginner Python course. How can I enroll?",
            normalized_content="i want to buy a beginner python course how can i enroll", timestamp=utcnow())
        session.add(message)
        session.flush()
        run = AnalysisRun(user_id=user.id, product_id=product.id, batch_id=batch.id,
            product_snapshot=ProductOut.model_validate(product).model_dump(mode="json", exclude={"created_at"}),
            config_snapshot=RunConfig(provider_mode="mock").model_dump(), idempotency_key=uuid4().hex,
            total_count=1)
        session.add(run)
        session.commit()
        run_id, user_id, message_id = run.id, user.id, message.id

    entered, release = Event(), Event()

    class Blocking(MockProvider):
        def qualify(self, product, target, context):
            entered.set()
            assert release.wait(20)
            return super().qualify(product, target, context)

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(process_one, factory, Blocking())
        try:
            assert entered.wait(20)
            assert process_one(factory, MockProvider()) is False
            with factory() as session:
                current = session.get(AnalysisRun, run_id)
                current.heartbeat_at = utcnow().replace(year=utcnow().year - 1)
                session.commit()
            recover_interrupted(factory)
            with factory() as session:
                current = retry_run(session, run_id, user_id, "postgres-retry-1")
                assert current.attempt_no == 2 and current.status == "queued"
        finally:
            release.set()
        assert task.result(timeout=30)

    with factory() as session:
        current = session.get(AnalysisRun, run_id)
        assert current.status == "queued" and current.attempt_no == 2
        assert session.scalar(select(func.count()).select_from(Analysis).where(
            Analysis.run_id == run_id, Analysis.message_id == message_id)) == 0
        assert session.scalar(select(Usage).where(Usage.run_id == run_id, Usage.run_attempt_no == 1)) is not None

    assert process_one(factory, MockProvider())
    with factory() as session:
        current = session.get(AnalysisRun, run_id)
        assert current.status == "completed" and current.processed_count == 1
        assert session.scalar(select(func.count()).select_from(Analysis).where(
            Analysis.run_id == run_id, Analysis.message_id == message_id)) == 1
