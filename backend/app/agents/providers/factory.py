from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from app.agents.providers.base import StructuredProvider
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


def get_provider(mode: str) -> StructuredProvider:
    if mode == "mock":
        return MockProvider()
    if mode == "real":
        client = _real_client.get()
        if client is not None:
            return RealProvider(client=client)
        return RealProvider()
    raise ValueError(f"Provider {mode!r} is not configured; no fallback to Mock is allowed")
