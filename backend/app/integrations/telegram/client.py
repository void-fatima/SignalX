"""Official Bot API only. No retries; token-bearing HTTP errors never escape."""
import logging
import re
from contextlib import nullcontext
from urllib.parse import urlsplit

import httpx

from app.core.errors import AppError
from app.integrations.telegram.config import TelegramSettings


class TelegramError(AppError):
    def __init__(self, category: str, *, http_status: int | None = None,
                 retry_after: int | None = None, delivery_uncertain: bool = False):
        super().__init__("telegram_" + category, "Telegram request failed: " + category, 502)
        self.category, self.http_status = category, http_status
        self.retry_after, self.delivery_uncertain = retry_after, delivery_uncertain


class _RedactTelegramLogs(logging.Filter):
    def __init__(self):
        super().__init__()
        self.secrets = set()

    def filter(self, record):
        # Telegram embeds credentials in URLs; httpx logs every request at INFO.
        record.msg = re.sub(r"/bot[0-9]+:[A-Za-z0-9_-]+", "/bot[REDACTED]", record.getMessage())
        for secret in tuple(self.secrets):
            record.msg = record.msg.replace(secret, "[REDACTED]")
        record.args = ()
        return True


def _positive_int(value) -> bool:
    return type(value) is int and value > 0


class TelegramClient:
    def __init__(self, config: TelegramSettings, *, client: httpx.Client | None = None):
        self.config = config
        self._token = config.require_token()
        self._client = client
        for name in ("httpx", "httpcore.http11", "httpcore.connection", "httpcore.proxy"):
            logger = logging.getLogger(name)
            filters = [f for f in logger.filters if isinstance(f, _RedactTelegramLogs)]
            if not filters:
                filters = [_RedactTelegramLogs()]
                logger.addFilter(filters[0])
            for filter in filters:
                filter.secrets.add(self._token)
                if config.webhook_secret and config.webhook_secret.get_secret_value():
                    filter.secrets.add(config.webhook_secret.get_secret_value())

    def _call(self, method: str, payload: dict):
        manager = nullcontext(self._client) if self._client is not None else httpx.Client(
            timeout=self.config.timeout_seconds, follow_redirects=False)
        try:
            with manager as client:
                response = client.post("https://api.telegram.org/bot" + self._token + "/" + method,
                    json=payload, timeout=self.config.timeout_seconds, follow_redirects=False)
        except (httpx.HTTPError, RuntimeError) as exc:
            # A timeout can happen after Telegram accepted a send. Never resend automatically.
            raise TelegramError("timeout" if isinstance(exc, httpx.TimeoutException) else "transport",
                                delivery_uncertain=method == "sendMessage") from None
        try:
            body = response.json()
        except (ValueError, RecursionError):
            body = None
        error_code = body.get("error_code") if isinstance(body, dict) else None
        status = response.status_code if not response.is_success else error_code if type(error_code) is int else None
        if not response.is_success or (isinstance(body, dict) and body.get("ok") is False):
            category = {400: "invalid_request", 401: "authentication", 403: "permission",
                        429: "rate_limit"}.get(status, "server" if type(status) is int and status >= 500 else "provider")
            params = body.get("parameters") if isinstance(body, dict) else None
            retry = params.get("retry_after") if isinstance(params, dict) else None
            raise TelegramError(category, http_status=response.status_code,
                retry_after=retry if _positive_int(retry) else None,
                delivery_uncertain=method == "sendMessage" and (type(status) is not int or status >= 500))
        if not isinstance(body, dict) or body.get("ok") is not True or "result" not in body:
            raise TelegramError("invalid_response", delivery_uncertain=method == "sendMessage")
        return body["result"]

    def get_me(self) -> dict:
        result = self._call("getMe", {})
        if not isinstance(result, dict) or not _positive_int(result.get("id")) or result.get("is_bot") is not True:
            raise TelegramError("invalid_response")
        return {key: result.get(key) for key in ("id", "is_bot", "username", "first_name", "can_read_all_group_messages")}

    def send_message(self, *, chat_id: int, message_id: int, text: str, thread_id: int | None = None) -> int:
        if type(chat_id) is not int or not chat_id or not _positive_int(message_id) or not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise AppError("invalid_reply", "Reply requires original chat/message and 1–4000 nonblank characters", 422)
        payload = {"chat_id": chat_id, "text": text,
            "reply_parameters": {"message_id": message_id, "allow_sending_without_reply": False},
            "link_preview_options": {"is_disabled": True}}
        if thread_id is not None:
            if not _positive_int(thread_id):
                raise AppError("invalid_reply", "Topic ID is invalid", 422)
            payload["message_thread_id"] = thread_id
        result = self._call("sendMessage", payload)
        if (not isinstance(result, dict) or not _positive_int(result.get("message_id"))
                or not isinstance(result.get("chat"), dict) or result["chat"].get("id") != chat_id):
            raise TelegramError("invalid_response", delivery_uncertain=True)
        return result["message_id"]

    def set_webhook(self, url: str) -> bool:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path != self.config.webhook_path
                or "<" in url or ">" in url):
            raise AppError("invalid_webhook_url", "Use an HTTPS public URL with the configured webhook path", 422)
        result = self._call("setWebhook", {"url": url, "secret_token": self.config.require_secret(),
            "allowed_updates": ["message"], "drop_pending_updates": False})
        if result is not True:
            raise TelegramError("invalid_response")
        return True

    def get_webhook_info(self) -> dict:
        result = self._call("getWebhookInfo", {})
        if not isinstance(result, dict):
            raise TelegramError("invalid_response")
        # Do not echo Telegram's free-form last_error_message or raw result.
        return {key: result.get(key) for key in ("url", "pending_update_count", "last_error_date", "allowed_updates")}

    def delete_webhook(self) -> bool:
        result = self._call("deleteWebhook", {"drop_pending_updates": False})
        if result is not True:
            raise TelegramError("invalid_response")
        return True
