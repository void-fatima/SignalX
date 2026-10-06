from typing import Protocol
from abc import ABC, abstractmethod
from app.agents.contracts import AgentInput, AgentOutput, ProductSnapshot, TargetMessage, Qualification, QualificationResult, UsageEvent, UsageInfo


class BaseProvider(ABC):
    """Structured Agent boundary. Implementations must not access persistence."""

    @abstractmethod
    def analyze(self, inputs: AgentInput) -> AgentOutput:
        """Return structured Agent data; optional scoring is owned by application code."""
        raise NotImplementedError


class Provider(Protocol):
    def qualify(self, product: ProductSnapshot, target: TargetMessage, context: list[TargetMessage]) -> tuple[Qualification, list[UsageEvent]]: ...


class StructuredProvider(Provider, Protocol):
    """Qualification-only boundary used by the public Agent orchestrator."""
    provider_mode: str

    def qualify_structured(self, product: ProductSnapshot, target: TargetMessage,
                          context: list[TargetMessage]) -> tuple[QualificationResult, list[UsageInfo]]: ...


class ProviderError(Exception):
    def __init__(self, message: str, usage: list[UsageEvent] | list[UsageInfo]):
        super().__init__(message)
        self.usage = usage
