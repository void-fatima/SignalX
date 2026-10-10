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
