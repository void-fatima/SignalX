from typing import Protocol
from app.agents.contracts import ProductSnapshot, TargetMessage, Qualification, UsageEvent


class Provider(Protocol):
    def qualify(self, product: ProductSnapshot, target: TargetMessage, context: list[TargetMessage]) -> tuple[Qualification, list[UsageEvent]]: ...


class ProviderError(Exception):
    def __init__(self, message: str, usage: list[UsageEvent]):
        super().__init__(message)
        self.usage = usage
