"""Explicit manual Bot API helpers. Import/--help never issue requests."""
import argparse
import json

from app.core.errors import AppError
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.config import telegram_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit Telegram bot operations; never prints credentials")
    parser.add_argument("operation", choices=("get-me", "set-webhook", "get-webhook-info", "delete-webhook"))
    parser.add_argument("--url", help="Public HTTPS backend URL, required only for set-webhook")
    args = parser.parse_args(argv)
    if args.operation == "set-webhook" and not args.url:
        parser.error("set-webhook requires --url")
    try:
        config = telegram_settings()
        client = TelegramClient(config)
        methods = {"get-me": client.get_me, "get-webhook-info": client.get_webhook_info, "delete-webhook": client.delete_webhook}
        result = client.set_webhook(args.url) if args.operation == "set-webhook" else methods[args.operation]()
        text = json.dumps({"status": "success", "operation": args.operation, "result": result}, ensure_ascii=False)
        for value in (config.bot_token, config.webhook_secret):
            if value and value.get_secret_value():
                text = text.replace(value.get_secret_value(), "[REDACTED]")
        print(text)
        return 0
    except AppError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "message": exc.message}))
        return 1
    except Exception:
        print(json.dumps({"status": "error", "message": "Telegram helper failed; raw errors suppressed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
