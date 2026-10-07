"""Environment-only Gemini settings; the official Chat endpoint is allowlisted."""
import os

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.providers.base import ProviderError

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_SMOKE_MODEL = "gemini-3.5-flash-lite"


def _trusted_url(value: str) -> str:
    if not isinstance(value, str) or value.strip().removesuffix("/") != GEMINI_BASE_URL.rstrip("/"):
        raise ValueError("Gemini base URL must be the official OpenAI-compatible endpoint")
    return GEMINI_BASE_URL


class GeminiProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    model: str = Field(min_length=1)
    base_url: str = GEMINI_BASE_URL
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_output_tokens: int = Field(default=2000, ge=100, le=10000)

    @field_validator("base_url")
    @classmethod
    def trusted_endpoint(cls, value: str) -> str:
        return _trusted_url(value)

    @field_validator("model")
    @classmethod
    def nonblank_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Gemini model is required")
        return value.strip()

    @property
    def chat_url(self) -> str:
        # Recheck before every dispatch, including after a caller's mutation.
        try:
            return _trusted_url(self.base_url) + "chat/completions"
        except ValueError:
            raise ProviderError("GEMINI_BASE_URL must be the official Chat Completions endpoint", []) from None

    def require_valid(self) -> None:
        try:
            type(self).model_validate(self.model_dump(), strict=True)
        except ValueError:
            raise ProviderError("Gemini configuration is invalid; check GEMINI_MODEL, GEMINI_BASE_URL and optional settings", []) from None

    @classmethod
    def from_env(cls) -> "GeminiProviderConfig":
        try:
            return cls(model=os.environ.get("GEMINI_MODEL", ""),
                base_url=os.environ.get("GEMINI_BASE_URL", GEMINI_BASE_URL),
                timeout_seconds=os.environ.get("GEMINI_TIMEOUT_SECONDS", "30"),
                max_output_tokens=os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "2000"))
        except ValueError:
            raise ProviderError("Gemini provider is not configured: check GEMINI_MODEL, GEMINI_BASE_URL and optional settings", []) from None
