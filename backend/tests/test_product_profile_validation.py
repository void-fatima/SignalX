"""Product request validation and ownership regressions, entirely offline."""
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import Product
from app.schemas.api import ProductInput, ProductPatch


PROFILE = {
    "name": "SensorWorks",
    "description": "Calibration and repairs for precision sensors.",
    "target_customer": "Laboratories that need reliable measurements.",
}
REQUIRED_FIELDS = tuple(PROFILE)


def create_product(client, **changes):
    response = client.post("/api/v1/products", json={**PROFILE, **changes})
    assert response.status_code == 201, response.json()
    return response.json()


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
@pytest.mark.parametrize("value", ["", " ", "\t\r\n ", "\u00a0\u2003\u3000", None])
def test_create_rejects_blank_or_null_without_persisting(client, factory, field, value):
    response = client.post("/api/v1/products", json={**PROFILE, field: value})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert any(item["field"] == f"body.{field}" for item in error["details"])
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 0


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
@pytest.mark.parametrize("value", ["", " ", "\t\r\n ", "\u00a0\u2003\u3000", None])
def test_patch_rejects_blank_or_null_atomically(client, field, value):
    product = create_product(client)
    path = f"/api/v1/products/{product['id']}"
    # Include another valid change to check that failed updates are atomic.
    response = client.patch(path, json={"price": "9.50", field: value})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert client.get(path).json() == product


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_create_requires_each_profile_field(client, field):
    payload = {key: value for key, value in PROFILE.items() if key != field}
    assert client.post("/api/v1/products", json=payload).status_code == 422


@pytest.mark.parametrize("field,limit", [("name", 200), ("description", 4000), ("target_customer", 2000)])
def test_existing_length_limits_for_create_and_patch(client, field, limit):
    product = create_product(client, **{field: "x" * limit})
    path = f"/api/v1/products/{product['id']}"
    assert client.patch(path, json={field: "y" * limit}).status_code == 200
    assert client.post("/api/v1/products", json={**PROFILE, field: "x" * (limit + 1)}).status_code == 422
    assert client.patch(path, json={field: "x" * (limit + 1)}).status_code == 422
    assert client.get(path).json()[field] == "y" * limit


@pytest.mark.parametrize("text", ["A valid profile", "  A valid profile \n", "خدمات کالیبراسیون برای آزمایشگاه‌ها"])
def test_valid_text_is_preserved_on_create_and_partial_update(client, text):
    product = create_product(client, **{field: text for field in REQUIRED_FIELDS})
    assert all(product[field] == text for field in REQUIRED_FIELDS)
    path = f"/api/v1/products/{product['id']}"
    response = client.patch(path, json={"description": text + " updated"})
    assert response.status_code == 200
    assert response.json()["description"] == text + " updated"
    assert response.json()["name"] == response.json()["target_customer"] == text
    assert client.get(path).json() == response.json()


def test_optional_defaults_noop_patch_and_price_clear(client):
    product = create_product(client)
    assert product["price"] is None and product["currency"] == "USD"
    assert all(product[field] == [] for field in ("problems_solved", "best_fit", "not_fit"))
    path = f"/api/v1/products/{product['id']}"
    assert client.patch(path, json={}).json() == product
    optional = {"problems_solved": ["  Keep spacing  "], "best_fit": ["Labs"],
                "not_fit": [], "price": "12.50", "currency": "EUR"}
    updated = client.patch(path, json=optional)
    assert updated.status_code == 200
    assert all(updated.json()[field] == value for field, value in optional.items())
    assert all(updated.json()[field] == PROFILE[field] for field in REQUIRED_FIELDS)
    cleared = client.patch(path, json={"price": None, "best_fit": []})
    assert cleared.status_code == 200 and cleared.json()["price"] is None
    assert cleared.json()["best_fit"] == []
    assert cleared.json()["problems_solved"] == optional["problems_solved"]
    created_with_optional = create_product(client, **optional)
    assert all(created_with_optional[field] == value for field, value in optional.items())


@pytest.mark.parametrize("field", ["problems_solved", "best_fit", "not_fit", "currency"])
def test_nonprice_optional_null_behavior_unchanged(client, field):
    assert client.post("/api/v1/products", json={**PROFILE, field: None}).status_code == 422
    product = create_product(client)
    path = f"/api/v1/products/{product['id']}"
    assert client.patch(path, json={field: None}).status_code == 422
    assert client.get(path).json() == product


@pytest.mark.parametrize("changes", [{"price": "-1"}, {"price": "1.234"}, {"price": "10000000000"},
                                      {"currency": "usd"}, {"currency": "EU"}, {"best_fit": "Labs"}])
def test_existing_optional_validation_preserved(client, changes):
    assert client.post("/api/v1/products", json={**PROFILE, **changes}).status_code == 422
    product = create_product(client)
    path = f"/api/v1/products/{product['id']}"
    assert client.patch(path, json=changes).status_code == 422
    assert client.get(path).json() == product


def test_patch_schema_retains_unset_and_explicit_null_semantics():
    assert ProductPatch().model_dump(exclude_unset=True) == {}
    assert ProductPatch(name=None, price=None).model_dump(exclude_unset=True) == {"name": None, "price": None}
    assert ProductPatch(price="0.00").price == Decimal("0.00")
    assert ProductInput(**PROFILE).model_dump()["problems_solved"] == []


def test_unknown_fields_still_ignored_and_cannot_reassign_owner(client, factory):
    owner = client.get("/api/v1/auth/me").json()["id"]
    forged = {"user_id": str(uuid4()), "owner_user_id": str(uuid4()), "unexpected": "ignored"}
    product = create_product(client, **forged)
    path = f"/api/v1/products/{product['id']}"
    assert not set(forged).intersection(product)
    patched = client.patch(path, json={**forged, "description": "Updated calibration service"})
    assert patched.status_code == 200
    assert patched.json()["description"] == "Updated calibration service"
    assert not set(forged).intersection(patched.json())
    with factory() as session:
        assert session.get(Product, product["id"]).user_id == owner


def test_own_listing_and_foreign_read_update_are_isolated(client):
    product = create_product(client)
    path = f"/api/v1/products/{product['id']}"
    with TestClient(app) as other:
        credentials = {"email": "profile-other@example.test", "password": "offline-test-password"}
        assert other.post("/api/v1/auth/register", json=credentials).status_code == 201
        assert other.post("/api/v1/auth/login", json=credentials).status_code == 200
        assert other.get("/api/v1/products").json()["items"] == []
        assert other.get(path).status_code == 404
        assert other.patch(path, json={"name": "Foreign update"}).status_code == 404
        own_product = create_product(other, name="Another laboratory service")
        assert other.get("/api/v1/products").json()["items"] == [own_product]
    assert client.get(path).json() == product
    assert client.get("/api/v1/products").json()["items"] == [product]
    assert client.get(f"/api/v1/products/{own_product['id']}").status_code == 404
    assert client.patch(f"/api/v1/products/{own_product['id']}", json={"name": "Foreign update"}).status_code == 404


def test_existing_session_requirement_is_preserved(app_client):
    path = f"/api/v1/products/{uuid4()}"
    assert app_client.post("/api/v1/products", json=PROFILE).status_code == 401
    assert app_client.get("/api/v1/products").status_code == 401
    assert app_client.get(path).status_code == 401
    assert app_client.patch(path, json={"name": "Valid name"}).status_code == 401


def test_historical_whitespace_profile_remains_readable_and_editable(client, factory):
    product = create_product(client)
    with factory() as session:
        row = session.get(Product, product["id"])
        row.name = " \t "
        session.commit()
    path = f"/api/v1/products/{product['id']}"
    assert client.get(path).json()["name"] == " \t "
    assert client.get("/api/v1/products").json()["items"][0]["name"] == " \t "
    assert client.patch(path, json={"description": "Updated calibration service"}).status_code == 200
    assert client.patch(path, json={"name": "Repaired profile"}).json()["name"] == "Repaired profile"


def test_product_openapi_schemas_match_published_contract():
    published = json.loads((Path(__file__).resolve().parents[2] / "contracts/openapi.json").read_text(encoding="utf-8"))
    generated = app.openapi()
    for name in ("ProductInput", "ProductPatch", "ProductOut", "Page_ProductOut_"):
        assert generated["components"]["schemas"][name] == published["components"]["schemas"][name]
