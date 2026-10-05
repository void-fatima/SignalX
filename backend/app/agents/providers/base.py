from typing import Protocol
from abc import ABC, abstractmethod
from app.agents.contracts import AgentInput, AgentOutput, ProductSnapshot, TargetMessage, Qualification, UsageEvent


class BaseProvider(ABC):
    """Structured Agent boundary. Implementations must not access persistence."""

    @abstractmethod
    def analyze(self, inputs: AgentInput) -> AgentOutput:
        """Return screening, qualification, scoring and usage; no side effects in DB."""
        raise NotImplementedError


class Provider(Protocol):
    def qualify(self, product: ProductSnapshot, target: TargetMessage, context: list[TargetMessage]) -> tuple[Qualification, list[UsageEvent]]: ...


class ProviderError(Exception):
    def __init__(self, message: str, usage: list[UsageEvent]):
        super().__init__(message)
        self.usage = usage
