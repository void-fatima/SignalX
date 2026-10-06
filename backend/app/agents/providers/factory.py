from app.agents.providers.base import StructuredProvider
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider


def get_provider(mode: str) -> StructuredProvider:
    if mode == "mock":
        return MockProvider()
    if mode == "real":
        return RealProvider()
    raise ValueError(f"Provider {mode!r} is not configured; no fallback to Mock is allowed")
