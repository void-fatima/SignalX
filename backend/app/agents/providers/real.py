"""Fail-closed integration slot. No provider/model has been selected yet."""
from app.agents.contracts import ProductSnapshot, TargetMessage, Qualification, UsageEvent


class RealProvider:
    def qualify(self, product: ProductSnapshot, target: TargetMessage, context: list[TargetMessage]) -> tuple[Qualification, list[UsageEvent]]:
        raise RuntimeError("RealProvider is not implemented: select a model, credentials, rates and usage contract first")


# Deliberately not registered in factory.py. Do not substitute Mock or claim usage
# for a request that was never sent. Future implementation must preserve attempts
# in ProviderError and use the prompt builders with structured-output validation.
