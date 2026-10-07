"""Additive backend contracts and fixtures, without changing the frozen Agent schema."""
import asyncio
import json
from pathlib import Path

import pytest

from app.auth.contracts import CurrentUser
from app.integrations.telegram.schemas import TelegramLeadOut
from app.main import app, unexpected_error
from app.schemas.api import ProductOut, ImportOut, RunOut, LeadDetail

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("filename,schema", [
    ("current_user.json", CurrentUser), ("product.json", ProductOut), ("import.json", ImportOut),
    ("run.json", RunOut), ("lead.json", LeadDetail), ("telegram_lead.json", TelegramLeadOut),
    ("failed_run.json", RunOut), ("failed_lead.json", LeadDetail), ("failed_telegram_lead.json", TelegramLeadOut),
])
def test_all_shared_backend_fixtures_remain_valid(filename, schema):
    record = schema.model_validate_json((ROOT / "contracts/examples" / filename).read_text(encoding="utf-8"))
    schema.model_validate_json(record.model_dump_json())


def test_exported_openapi_is_in_sync_and_retry_uses_required_key():
    exported = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))
    assert exported == app.openapi()
    retry = exported["paths"]["/api/v1/analysis/runs/{id}/retry"]["post"]
    assert next(p for p in retry["parameters"] if p["name"] == "Idempotency-Key")["required"]
    assert "202" in retry["responses"]
    send = exported["paths"]["/api/v1/leads/{lead_id}/telegram/reply"]["post"]
    assert not next(p for p in send["parameters"] if p["name"] == "Idempotency-Key")["required"]


def test_unexpected_api_error_does_not_log_exception_credentials(caplog):
    private = "fake-credential-in-unsafe-exception"
    response = asyncio.run(unexpected_error(None, RuntimeError(private)))
    assert response.status_code == 500 and private not in response.body.decode()
    assert private not in caplog.text and "sensitive exception details withheld" in caplog.text
