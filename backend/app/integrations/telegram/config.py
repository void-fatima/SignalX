import re
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.errors import AppError


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TELEGRAM_",
        env_file=(Path(__file__).resolve().parents[4] / ".env", Path(__file__).resolve().parents[3] / ".env"),
        extra="ignore", hide_input_in_errors=True)
    bot_token: SecretStr | None = Field(default=None, repr=False)
    webhook_secret: SecretStr | None = Field(default=None, repr=False)
    webhook_path: str = "/integrations/telegram/webhook"
    timeout_seconds: float = Field(default=15, gt=0, le=60)

    def require_token(self) -> str:
        value = self.bot_token.get_secret_value() if self.bot_token else ""
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", value):
            raise AppError("telegram_configuration", "A valid TELEGRAM_BOT_TOKEN is required", 503)
        return value

    def require_secret(self) -> str:
        value = self.webhook_secret.get_secret_value() if self.webhook_secret else ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value):
            raise AppError("telegram_configuration", "A valid TELEGRAM_WEBHOOK_SECRET is required", 503)
        return value


def telegram_settings() -> TelegramSettings:
    try:
        config = TelegramSettings()
        if config.webhook_path != "/integrations/telegram/webhook":
            raise ValueError("unsupported webhook path")
        return config
    except ValueError:
        raise AppError("telegram_configuration", "Check Telegram environment settings", 503) from None
