from app.agents.contracts import ProductSnapshot, TargetMessage, RunConfig, AnalysisResult, UsageEvent
from app.agents.context import select_context
from app.agents.screening import screen
from app.agents.scoring import score
from app.agents.providers.base import Provider
from app.agents.providers.factory import get_provider
from app.agents.qualification import validate_qualification


def analyze(product: ProductSnapshot, target: TargetMessage, messages: list[TargetMessage], config: RunConfig, provider: Provider) -> tuple[AnalysisResult, list[UsageEvent]]:
    context = select_context(target, messages, config)
    screening = screen(product, target, context)
    if not screening.is_candidate:
        return AnalysisResult(is_candidate=False, screening_reason=screening.reason, reason=screening.reason), []
    qualification, usage = provider.qualify(product, target, context)
    qualification, valid = validate_qualification(qualification, target, context, usage)
    value, decision, decision_reason = score(qualification.signals, valid, qualification.needs_human_review)
    return AnalysisResult(is_candidate=True, screening_reason=screening.reason,
        **qualification.model_dump(exclude={"needs_human_review"}), lead_score=value, decision=decision,
        decision_reason=decision_reason, context_message_ids=[m.id for m in context]), usage
