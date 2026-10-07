"""The existing manual CSV smoke helper remains authenticated and mock-only."""
import importlib.util
import io
import json
from pathlib import Path

import pytest
from urllib.error import HTTPError
from urllib.request import Request


@pytest.fixture
def smoke():
    path = Path(__file__).resolve().parents[2] / "scripts/smoke.py"
    spec = importlib.util.spec_from_file_location("signalx_csv_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manual_helper_requires_auth_before_requests(smoke, monkeypatch):
    monkeypatch.delenv("SMOKE_SESSION_TOKEN", raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail("No HTTP request may happen without a configured session")
    monkeypatch.setattr(smoke, "request", forbidden)
    with pytest.raises(SystemExit, match="SMOKE_SESSION_TOKEN"):
        smoke.main()


def test_manual_helper_attaches_existing_session_without_printing(smoke, monkeypatch, capsys):
    monkeypatch.setenv("SMOKE_SESSION_TOKEN", "fake-offline-smoke-session")
    calls = []
    class Response(io.BytesIO):
        status = 200
    def open_fake(request, timeout):
        calls.append(request)
        return Response(json.dumps({"status": "ok"}).encode())
    monkeypatch.setattr(smoke.opener, "open", open_fake)
    assert smoke.request("/products")[0] == 200
    assert calls[0].get_header("Authorization") == "Bearer fake-offline-smoke-session"
    assert "fake-offline-smoke-session" not in capsys.readouterr().out


def test_manual_helper_never_queues_real_provider_work(smoke, monkeypatch):
    monkeypatch.setenv("SMOKE_SESSION_TOKEN", "fake-offline-smoke-session")
    calls = []
    def request(path):
        calls.append(path)
        return 200, {"provider_mode": "real"}
    monkeypatch.setattr(smoke, "request", request)
    with pytest.raises(SystemExit, match="requires mock"):
        smoke.main()
    assert calls == ["/health"]


def test_manual_helper_rejects_remote_plaintext_and_credential_redirects(smoke, monkeypatch):
    monkeypatch.setenv("SMOKE_SESSION_TOKEN", "fake-offline-smoke-session")
    monkeypatch.setattr(smoke, "base", "http://remote.example/api/v1")
    with pytest.raises(SystemExit, match="HTTPS"):
        smoke.main()
    assert smoke.NoRedirect().redirect_request(Request("https://trusted.example"), None, 302,
        "Found", {}, "https://other.example") is None
