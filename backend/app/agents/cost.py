"""Pure accounting utilities. Rates are supplied, never invented or fetched here."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class PriceRates(BaseModel):
    model: str
    version: str
    input_usd_per_million: Decimal = Field(ge=0, allow_inf_nan=False)
    output_usd_per_million: Decimal = Field(ge=0, allow_inf_nan=False)


class CostEstimate(BaseModel):
    cost_usd: Decimal | None
    cost_status: Literal["mock", "known", "unknown"]
    price_version: str | None


def calculate_cost(
    provider_mode: Literal["mock", "real"],
    input_tokens: int | None,
    output_tokens: int | None,
    rates: PriceRates | None,
) -> CostEstimate:
    for tokens in (input_tokens, output_tokens):
        if tokens is not None and (type(tokens) is not int or tokens < 0):
            raise ValueError("Token counts must be non-negative integers or unknown")
    if provider_mode == "mock":
        return CostEstimate(cost_usd=Decimal("0"), cost_status="mock", price_version="mock_v1")
    if provider_mode != "real":
        raise ValueError("Unsupported provider mode")
    if rates is None or input_tokens is None or output_tokens is None:
        return CostEstimate(cost_usd=None, cost_status="unknown", price_version=rates.version if rates else None)
    amount = (input_tokens * rates.input_usd_per_million + output_tokens * rates.output_usd_per_million) / Decimal(1_000_000)
    return CostEstimate(cost_usd=amount, cost_status="known", price_version=rates.version)


def cost_per(costs: list[CostEstimate], denominator: int) -> Decimal | None:
    """Do not report incomplete or zero-denominator per-message/per-lead costs."""
    if denominator <= 0 or any(c.cost_usd is None or c.cost_status == "unknown" for c in costs):
        return None
    if len({c.cost_status for c in costs}) > 1:
        raise ValueError("Mock and real accounting must be reported separately")
    return sum((c.cost_usd for c in costs), Decimal("0")) / denominator
