"""Offline Bot API normalization/config/security tests; all HTTP is mocked."""
import json
import logging

import httpx
import pytest
from pydantic import SecretStr

from app.core.errors import AppError
from app.integrations.telegram import manage
from app.integrations.telegram.client import TelegramClient, TelegramError
from app.integrations.telegram.config import TelegramSettings
from app.integrations.telegram.normalization import normalize_update

TOKEN = "123456:fake-telegram-bot-token"
SECRET = "fake-telegram-webhook-secret"


def config():
    return TelegramSettings(_env_file=None, bot_token=SecretStr(TOKEN), webhook_secret=SecretStr(SECRET))


def update(text="I'm looking for a Python course. How much?", **changes):
    message = dict(message_id=7, date=1791360000, chat=dict(id=-100123, type="supergroup", title="Test group"),
                   **{"from": dict(id=8, is_bot=False, first_name="Test", last_name="User", username="test_user")}, text=text)
    message.update(changes)
    return dict(update_id=10, message=message)


@pytest.mark.parametrize("text", ["I'm looking for a Python course. How much?", "دنبال دوره پایتون هستم. قیمتش چقدره؟"])
def test_normal_text_preserves_source_and_aware_timestamp(text):
    source = normalize_update(update(text, message_thread_id=12, reply_to_message=dict(message_id=6, chat=dict(id=-100123))))
    assert source.text == text and source.source == "telegram" and source.timestamp.tzinfo is not None
    assert source.update_id == 10 and source.chat_id == -100123 and source.message_id == 7
    assert source.chat_title == "Test group" and source.sender_display_name == "Test User"
    assert source.sender_id == 8 and source.sender_username == "test_user"
    assert source.reply_to_message_id == 6 and source.message_thread_id == 12
    assert source.conversation_id == "telegram:-100123:topic:12"


@pytest.mark.parametrize("kind", ["bot", "media", "service", "channel", "private", "edited", "callback", "empty", "oversize", "bad_timestamp", "bad_sender", "bool_id"])
def test_unsupported_updates_are_ignored(kind):
    payload = update()
    message = payload["message"]
    if kind == "bot":
        message["from"]["is_bot"] = True
    elif kind == "media":
        message.pop("text")
        message["photo"] = []
    elif kind == "service":
        message["new_chat_members"] = []
    elif kind in {"channel", "private"}:
        message["chat"]["type"] = kind
    elif kind == "edited":
        payload["edited_message"] = payload.pop("message")
    elif kind == "callback":
        payload = dict(update_id=10, callback_query={})
    elif kind == "empty":
        message["text"] = " "
    elif kind == "oversize":
        message["text"] = "a" * 4001
    elif kind == "bad_timestamp":
        message["date"] = 10**100
    elif kind == "bad_sender":
        message["from"].pop("is_bot")
    else:
        message["message_id"] = True
    assert normalize_update(payload) is None


def test_foreign_parent_is_not_used_as_context():
    source = normalize_update(update(reply_to_message=dict(message_id=6, chat=dict(id=-999))))
    assert source.reply_to_message_id is None


def test_api_sends_only_explicit_call_and_preserves_reply_and_topic(caplog):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=dict(ok=True, result=dict(message_id=91, chat=dict(id=-100123))))
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = TelegramClient(config(), client=http)
        assert requests == []
        with caplog.at_level(logging.DEBUG):
            assert client.send_message(chat_id=-100123, message_id=7, thread_id=12, text="Approved by a human") == 91
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["reply_parameters"] == dict(message_id=7, allow_sending_without_reply=False)
    assert body["message_thread_id"] == 12 and body["chat_id"] == -100123
    assert "parse_mode" not in body and TOKEN not in caplog.text and SECRET not in caplog.text


@pytest.mark.parametrize("failure,category", [(400, "invalid_request"), (401, "authentication"),
    (403, "permission"), (429, "rate_limit"), (500, "server"), (503, "server"), ("timeout", "timeout"), ("network", "transport"), ("bad_json", "invalid_response")])
def test_api_failures_sanitized_bounded_and_delivery_uncertain(failure, category):
    requests = []
    def handle(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(TOKEN)
        if failure == "network":
            raise httpx.ConnectError(TOKEN)
        if failure == "bad_json":
            return httpx.Response(200, text=TOKEN)
        return httpx.Response(failure, json=dict(ok=False, description=TOKEN + SECRET, error_code=failure, parameters=dict(retry_after=5)))
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(TelegramError) as error:
            TelegramClient(config(), client=http).send_message(chat_id=-100123, message_id=7, text="Human reply")
    assert len(requests) == 1 and error.value.category == category
    assert TOKEN not in str(error.value) and SECRET not in str(error.value)
    assert error.value.delivery_uncertain is (failure in {500, 503, "timeout", "network", "bad_json"})


@pytest.mark.parametrize("text", ["", " ", "x" * 4001])
def test_invalid_reply_never_dispatches(text):
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("Unexpected send"))) as http:
        with pytest.raises(AppError):
            TelegramClient(config(), client=http).send_message(chat_id=-100123, message_id=7, text=text)


def test_webhook_helpers_do_not_drop_pending_updates_and_only_receive_messages():
    calls = []
    def handle(request):
        calls.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        result = dict(url="https://backend.example/integrations/telegram/webhook", pending_update_count=0) if len(calls) == 2 else True
        return httpx.Response(200, json=dict(ok=True, result=result))
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = TelegramClient(config(), client=http)
        assert client.set_webhook("https://backend.example/integrations/telegram/webhook")
        assert client.get_webhook_info()["pending_update_count"] == 0
        assert client.delete_webhook()
    assert calls[0][1]["secret_token"] == SECRET and calls[0][1]["allowed_updates"] == ["message"]
    assert calls[0][1]["drop_pending_updates"] is False and calls[2][1]["drop_pending_updates"] is False


@pytest.mark.parametrize("url", ["http://backend.example/integrations/telegram/webhook", "https://x.example/wrong", "https://user:secret@x.example/integrations/telegram/webhook", "https://x.example/integrations/telegram/webhook?token=secret"])
def test_invalid_webhook_url_never_dispatches(url):
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("Unexpected call"))) as http:
        with pytest.raises(AppError):
            TelegramClient(config(), client=http).set_webhook(url)


def test_cli_get_me_safe_output_and_no_raw_error(monkeypatch, capsys):
    monkeypatch.setattr(manage, "telegram_settings", config)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,
        json=dict(ok=True, result=dict(id=123, is_bot=True, username=TOKEN, first_name=SECRET)))))
    monkeypatch.setattr(manage, "TelegramClient", lambda c: TelegramClient(c, client=client))
    assert manage.main(["get-me"]) == 0
    output = capsys.readouterr().out
    assert TOKEN not in output and SECRET not in output and json.loads(output)["status"] == "success"
    client.close()


def test_cli_help_never_constructs_client(monkeypatch):
    monkeypatch.setattr(manage, "TelegramClient", lambda *a: pytest.fail("Unexpected client"))
    with pytest.raises(SystemExit) as error:
        manage.main(["--help"])
    assert error.value.code == 0


@pytest.mark.parametrize("chat_type", [[], {}, None])
def test_malformed_chat_type_is_safely_ignored(chat_type):
    payload = update()
    payload["message"]["chat"]["type"] = chat_type
    assert normalize_update(payload) is None


def test_malformed_api_error_code_remains_sanitized_failure():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,
        json=dict(ok=False, error_code={"private": TOKEN}, description=SECRET)))) as http:
        with pytest.raises(TelegramError) as exc:
            TelegramClient(config(), client=http).get_me()
    assert exc.value.category == "provider" and TOKEN not in str(exc.value) and SECRET not in str(exc.value)
