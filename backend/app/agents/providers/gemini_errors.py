"""Private Gemini failure diagnostics without raw errors, bodies or headers."""
import socket
import ssl

import httpx

GOOGLE_STATUSES = {
    "INVALID_ARGUMENT", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND",
    "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION", "UNAVAILABLE", "INTERNAL",
    "DEADLINE_EXCEEDED", "CANCELLED", "UNKNOWN", "UNIMPLEMENTED",
}
GOOGLE_CODES = GOOGLE_STATUSES | {
    "invalid_api_key", "invalid_request_error", "rate_limit_exceeded",
    "insufficient_quota", "model_not_found",
}
MESSAGES = {
    "authentication": "Google reports an authentication or invalid-key failure.",
    "permission": "Google reports a permission or access failure.",
    "schema_validation": "Google reports request schema or structured-output validation failure.",
    "request_validation": "Google reports an invalid request.",
    "rate_limit": "Google reports a request/token rate limit.",
    "quota_exceeded": "Google reports an account/model quota limit.",
    "quota_or_rate_limit": "Google reports resource exhaustion; quota versus rate limit is unspecified.",
    "model_or_endpoint": "Google reports an unavailable model or endpoint.",
    "server_error": "Google reports a server failure.",
    "provider_error": "Unrecognized provider message omitted for security.",
    "http_error": "Unrecognized provider message omitted for security.",
}


def _response_error(response: httpx.Response | None) -> tuple[dict, bool | None]:
    if response is None:
        return {}, False
    try:
        present = bool(response.content)
    except RuntimeError:
        present = None
    try:
        body = response.json()
    except (ValueError, RuntimeError, RecursionError):
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    return (error if isinstance(error, dict) else {}), present


def _google_category(status: int | None, error: dict) -> str:
    code, name = error.get("code"), error.get("status")
    code = code if type(code) is int or isinstance(code, str) else None
    name = name if isinstance(name, str) else None
    if status is not None and status < 400 and type(code) is int and 400 <= code <= 599:
        status = code
    message = error.get("message")
    text = message[:4096].casefold() if isinstance(message, str) else ""
    details = error.get("details")
    reasons = {item.get("reason") for item in details[:20]
               if isinstance(item, dict) and isinstance(item.get("reason"), str)} if isinstance(details, list) else set()
    if (status == 401 or name == "UNAUTHENTICATED" or code == "invalid_api_key"
            or "API_KEY_INVALID" in reasons
            or any(term in text for term in ("api key not valid", "invalid api key", "api_key_invalid"))):
        return "authentication"
    if status == 403 or name == "PERMISSION_DENIED":
        return "permission"
    if status == 429 or name == "RESOURCE_EXHAUSTED":
        if ("RATE_LIMIT_EXCEEDED" in reasons or code == "rate_limit_exceeded"
                or any(term in text for term in ("rate limit", "rate_limit", "per minute", "per_minute", "perminute"))):
            return "rate_limit"
        if "QUOTA_EXCEEDED" in reasons or code == "insufficient_quota" or "quota" in text:
            return "quota_exceeded"
        return "quota_or_rate_limit"
    if status == 400 or name == "INVALID_ARGUMENT":
        if any(term in text for term in ("schema", "response_format", "additionalproperties", "minlength", "maxlength")):
            return "schema_validation"
        return "request_validation"
    if status == 404 or name == "NOT_FOUND" or code == "model_not_found":
        return "model_or_endpoint"
    if (status is not None and status >= 500) or name in {"INTERNAL", "UNAVAILABLE"}:
        return "server_error"
    return "provider_error" if status is None or status < 400 else "http_error"


def _cause_category(exc: Exception) -> str | None:
    current, seen = exc, set()
    for _ in range(8):
        if id(current) in seen:
            break
        seen.add(id(current))
        for cls, category in ((ssl.SSLCertVerificationError, "tls_certificate_error"),
            (ssl.SSLError, "tls_error"), (socket.gaierror, "dns_resolution_error"),
            (ConnectionRefusedError, "connection_refused"), (ConnectionResetError, "connection_reset")):
            if isinstance(current, cls):
                return category
        current = current.__cause__ if current.__cause__ is not None else current.__context__
        if current is None:
            break
    return None


def request_failure(stage: str, attempt: int, timeout_seconds: float, *,
                    exc: Exception | None = None, response: httpx.Response | None = None) -> dict[str, object]:
    """Return measured/known metadata and fixed category summaries only.

    Google message text is interpreted for classification, never echoed or stored.
    Unknown provider codes/statuses, exception messages and causal messages are
    omitted rather than attempting to redact arbitrary credentials/user content.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
    error, present = _response_error(response)
    status = response.status_code if response is not None else None
    kind = "http" if status is not None and status >= 400 else "provider"
    category = _google_category(status, error)
    exception_type, cause = None, None
    if exc is not None and not isinstance(exc, httpx.HTTPStatusError):
        cause = _cause_category(exc)
        kind = "timeout" if isinstance(exc, httpx.TimeoutException) else "transport"
        mapping = ((httpx.ConnectTimeout, "connect_timeout"), (httpx.ReadTimeout, "read_timeout"),
            (httpx.WriteTimeout, "write_timeout"), (httpx.PoolTimeout, "pool_timeout"),
            (httpx.TimeoutException, "timeout"), (httpx.ProxyError, "proxy_error"),
            (httpx.ConnectError, "connection_error"), (httpx.ReadError, "read_error"),
            (httpx.WriteError, "write_error"), (httpx.CloseError, "close_error"),
            (httpx.RemoteProtocolError, "remote_protocol_error"), (httpx.LocalProtocolError, "local_protocol_error"),
            (httpx.UnsupportedProtocol, "unsupported_protocol"), (httpx.TooManyRedirects, "redirect_error"),
            (httpx.DecodingError, "decoding_error"), (httpx.NetworkError, "network_error"),
            (httpx.HTTPError, "transport_error"), (RuntimeError, "client_runtime_error"))
        for cls, candidate in mapping:
            if isinstance(exc, cls):
                category, exception_type = candidate, cls.__name__
                break
        if isinstance(exc, RuntimeError):
            kind = "client"
    elif isinstance(exc, httpx.HTTPStatusError):
        exception_type = "HTTPStatusError"
    code, google_status, message = error.get("code"), error.get("status"), error.get("message")
    safe_code = (code if type(code) is int and 0 <= code <= 599 else
                 code if isinstance(code, str) and code in GOOGLE_CODES else None)
    safe_status = google_status if isinstance(google_status, str) and google_status in GOOGLE_STATUSES else None
    return {"stage": stage, "attempt_no": attempt, "failure_kind": kind,
        "provider_error_category": category, "http_status": status, "response_body_existed": present,
        "google_error_code": safe_code, "google_error_status": safe_status,
        "google_error_message": MESSAGES.get(category, MESSAGES["provider_error"])
            if isinstance(message, str) and message.strip() else None,
        "google_error_message_is_category_summary": True,
        "exception_type": exception_type, "cause_category": cause, "timeout_seconds": timeout_seconds}
