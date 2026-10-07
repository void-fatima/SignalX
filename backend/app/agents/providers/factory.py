from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import os

import httpx

from app.agents.providers.base import ProviderError, StructuredProvider
from app.agents.providers.gemini import GeminiProvider
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider

_real_client: ContextVar[httpx.Client | None] = ContextVar("agent_real_client", default=None)


@contextmanager
def real_provider_client(client: httpx.Client) -> Iterator[None]:
    """Scoped caller-owned HTTP client for manual acceptance/evaluation tools.

    Default production construction is unchanged. Client injection never changes
    provider selection, credentials, prompts, validation or scoring.
    """
    token = _real_client.set(client)
    try:
        yield
    finally:
        _real_client.reset(token)


def configured_real_provider() -> str:
    """An absent selector preserves the existing Responses provider."""
    selection = os.environ.get("LLM_PROVIDER", "avalai").strip()
    if selection not in {"avalai", "gemini"}:
        raise ProviderError("LLM_PROVIDER must be avalai or gemini; no provider fallback is allowed", [])
    return selection


def get_provider(mode: str) -> StructuredProvider:
    if mode == "mock":
        return MockProvider()
    if mode == "real":
        provider = GeminiProvider if configured_real_provider() == "gemini" else RealProvider
        client = _real_client.get()
        if client is not None:
            return provider(client=client)
        return provider()
    raise ValueError(f"Provider {mode!r} is not configured; no fallback to Mock is allowed")
