"""Provider interface and deterministic Mock implementation."""
from app.agents.providers.base import BaseProvider
from app.agents.providers.mock import MockProvider

__all__ = ["BaseProvider", "MockProvider"]
