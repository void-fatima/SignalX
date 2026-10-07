"""Exercise a running API + separate worker. Run from root with backend Python."""
import json
import os
import time
import uuid
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError

root = Path(__file__).resolve().parents[1]
base = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8000/api/v1")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a session credential to an unexpected destination.
        return None


opener = build_opener(NoRedirect())


def request(path, data=None, headers=None):
    token = os.environ.get("SMOKE_SESSION_TOKEN", "").strip()
    if len(token) > 512 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise SystemExit("SMOKE_SESSION_TOKEN has an invalid format; no request was sent.")
    values = {**({"Authorization": "Bearer " + token} if token else {}), **(headers or {})}
    with opener.open(Request(base + path, data=data, headers=values), timeout=10) as response:
        return response.status, json.load(response)


def post(path, body, headers=None):
    return request(path, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})


def main():
    if not os.environ.get("SMOKE_SESSION_TOKEN", "").strip():
        raise SystemExit("Set SMOKE_SESSION_TOKEN to a valid session for your existing demo account; no credential is printed.")
    url = urlsplit(base)
    if (url.scheme not in {"http", "https"} or url.username or url.password or url.query or url.fragment
            or (url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"})):
        raise SystemExit("SMOKE_API_URL must use HTTPS or local loopback HTTP, without embedded credentials.")
    if request("/health")[1].get("provider_mode") != "mock":
        raise SystemExit("This synthetic CSV smoke helper requires mock mode; no analysis was queued.")
    assert request("/ready")[0] == 200
    status, product = post("/products", {"name": "Backend Course", "description": "دوره بک‌اند پروژه‌محور", "target_customer": "Developers"})
    assert status == 201
    boundary = "signalx-" + uuid.uuid4().hex
    content = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"community_name\"\r\n\r\nsmoke-demo\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"demo.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode()
    content += (root / "data" / "demo_messages.csv").read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    _, imported = request("/imports", content, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    body = {"product_id": product["id"], "batch_id": imported["batch"]["id"]}
    key = str(uuid.uuid4())
    status, run = post("/analysis/runs", body, {"Idempotency-Key": key})
    assert status == 202
    assert post("/analysis/runs", body, {"Idempotency-Key": key})[1]["id"] == run["id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        _, current = request(f"/analysis/runs/{run['id']}")
        if current["status"] in {"completed", "partial", "failed", "interrupted"}:
            break
        time.sleep(.25)
    assert current["status"] == "completed", current
    assert current["processed_count"] == 20
    _, leads = request(f"/leads?run_id={run['id']}&decision=respond")
    assert leads["total"] >= 1
    _, detail = request(f"/leads/{leads['items'][0]['id']}")
    assert detail["analysis"]["lead_score"] == 84
    assert detail["analysis"]["provider_mode"] == "mock"
    assert all(m["conversation_id"] == detail["message"]["conversation_id"] for m in detail["context"])
    for filename, value in [("product", product), ("import", imported), ("run", current), ("lead", detail)]:
        (root / "contracts" / "examples" / f"{filename}.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"HTTP smoke passed: 20 messages, {leads['total']} respond results, sample score 84; run={run['id']}")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        raise SystemExit(f"HTTP smoke failed (status {error.code}); check authentication and API configuration.") from None
