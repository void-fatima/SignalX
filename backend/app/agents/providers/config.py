"""Environment configuration for trusted Responses endpoints; no implicit model/key."""
import os
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.cost import PriceRates
from app.agents.providers.base import ProviderError

DEFAULT_BASE_URL = "https://api.openai.com/v1"
TRUSTED_BASE_URLS = frozenset({DEFAULT_BASE_URL, "https://api.avalai.ir/v1"})


def _trusted_base_url(value: str) -> str:
    # Exact canonical endpoints only: no credentials, query, fragment, extra
    # paths, ports or lookalike hosts. One optional trailing slash is harmless.
    if not isinstance(value, str):
        raise ValueError("Base URL must be a trusted Responses endpoint")
    normalized = value.strip().removesuffix("/")
    if normalized not in TRUSTED_BASE_URLS:
        raise ValueError("Base URL must be a trusted Responses endpoint")
    return normalized


class RealProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    model: str = Field(min_length=1)
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_output_tokens: int = Field(default=2000, ge=100, le=10000)
    rates: PriceRates | None = None

    @field_validator("base_url")
    @classmethod
    def trusted_endpoint(cls, value: str) -> str:
        return _trusted_base_url(value)

    @property
    def responses_url(self) -> str:
        # Recheck at request time: model_copy/mutation can bypass validators.
        try:
            return _trusted_base_url(self.base_url) + "/responses"
        except ValueError:
            raise ProviderError("OPENAI_BASE_URL must be a trusted Responses endpoint", []) from None

    @classmethod
    def from_env(cls) -> "RealProviderConfig":
        try:
            model = os.environ.get("OPENAI_MODEL", "").strip()
            if not model:
                raise ValueError("missing configuration")
            prices = [os.environ.get(name, "").strip() for name in (
                "OPENAI_PRICE_VERSION", "OPENAI_INPUT_USD_PER_MILLION", "OPENAI_OUTPUT_USD_PER_MILLION")]
            if any(prices) and not all(prices):
                raise ValueError("incomplete rates")
            rates = PriceRates(model=model, version=prices[0],
                input_usd_per_million=Decimal(prices[1]),
                output_usd_per_million=Decimal(prices[2])) if all(prices) else None
            return cls(model=model, rates=rates,
                base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL),
                timeout_seconds=os.environ.get("OPENAI_TIMEOUT_SECONDS", "30"),
                max_output_tokens=os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2000"))
        except (ValueError, ArithmeticError):
            # Validation errors can include input values. Never expose them.
            raise ProviderError("Real provider is not configured: check OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL and optional settings", []) from None

    def require_valid(self) -> None:
        self.responses_url
        if not self.model.strip():
            raise ProviderError("Real provider is not configured: model is required", [])
        if self.rates is not None and self.rates.model != self.model:
            raise ProviderError("Real provider price model must match the configured model", [])
        if self.rates is not None and not self.rates.version.strip():
            raise ProviderError("Real provider price version must not be empty", [])
