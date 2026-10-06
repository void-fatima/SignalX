import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.db.session import get_session
from app.main import app


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def app_client(factory):
    def dependency():
        with factory() as session:
            yield session
    app.dependency_overrides[get_session] = dependency
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_client):
    credentials = {"email": "default@example.test", "password": "correct horse battery"}
    registered = app_client.post("/api/v1/auth/register", json=credentials)
    assert registered.status_code == 201
    logged_in = app_client.post("/api/v1/auth/login", json=credentials)
    assert logged_in.status_code == 200
    yield app_client
