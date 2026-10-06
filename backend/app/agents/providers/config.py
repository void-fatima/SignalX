"""Environment configuration for qualification; no implicit model or credentials."""
import os
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.cost import PriceRates
from app.agents.providers.base import ProviderError


class RealProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_output_tokens: int = Field(default=2000, ge=100, le=10000)
    rates: PriceRates | None = None

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
                timeout_seconds=os.environ.get("OPENAI_TIMEOUT_SECONDS", "30"),
                max_output_tokens=os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2000"))
        except (ValueError, ArithmeticError):
            # Validation errors can include input values. Never expose them.
            raise ProviderError("Real provider is not configured: check OPENAI_API_KEY, OPENAI_MODEL and optional settings", []) from None

    def require_valid(self) -> None:
        if not self.model.strip():
            raise ProviderError("Real provider is not configured: model is required", [])
        if self.rates is not None and self.rates.model != self.model:
            raise ProviderError("Real provider price model must match the configured model", [])
        if self.rates is not None and not self.rates.version.strip():
            raise ProviderError("Real provider price version must not be empty", [])
