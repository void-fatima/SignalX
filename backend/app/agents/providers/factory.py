from app.agents.providers.base import Provider
from app.agents.providers.mock import MockProvider


def get_provider(mode: str) -> Provider:
    if mode == "mock":
        return MockProvider()
    raise ValueError(f"Provider {mode!r} is not configured; no fallback to Mock is allowed")
