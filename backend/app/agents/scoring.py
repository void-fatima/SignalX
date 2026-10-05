"""Pure, provider-independent deterministic scoring for SignalX."""
from app.agents.contracts import Decision, QualificationResult, ScoringResult, Signals

SCORING_VERSION = "score_v1"
WEIGHTS = {"purchase_intent": 30, "product_fit": 30, "need_strength": 15,
           "urgency": 10, "confidence": 10, "response_opportunity": 5}


def _score(
    signals: Signals | QualificationResult,
    valid_purchase_evidence: bool | None,
    needs_human_review: bool,
) -> tuple[int, Decision, str]:
    # Revalidate even previously constructed/mutated models; never mutate input.
    signals = Signals.model_validate({name: getattr(signals, name) for name in WEIGHTS})
    raw_score = (
        30 * signals.purchase_intent
        + 30 * signals.product_fit
        + 15 * signals.need_strength
        + 10 * signals.urgency
        + 10 * signals.confidence
        + 5 * signals.response_opportunity
    )
    # Python round(): exact half ties go to the nearest even integer.
    value = max(0, min(100, round(raw_score)))
    decision = Decision.RESPOND if value >= 70 else Decision.REVIEW if value >= 40 else Decision.IGNORE
    reason = "score_threshold_met"
    if decision == Decision.RESPOND:
        for condition, why in [
            (signals.confidence < .60, "low_confidence"),
            (signals.product_fit < .50, "low_product_fit"),
            (valid_purchase_evidence is not True, "invalid_purchase_evidence"),
            (needs_human_review, "human_review_required"),
        ]:
            if condition:
                decision, reason = Decision.REVIEW, why
                break
    return value, decision, reason


def calculate_score(
    signals: Signals | QualificationResult,
    valid_purchase_evidence: bool | None = None,
    needs_human_review: bool = False,
) -> ScoringResult:
    """score_v1 public scorer: evidence must be explicitly validated by the caller.

    Evidence presence alone does not establish validity. Missing/invalid evidence
    can only downgrade RESPOND; it does not change the score or upgrade IGNORE.
    """
    value, decision, _ = _score(signals, valid_purchase_evidence, needs_human_review)
    return ScoringResult(score=value, decision=decision)


def score(
    signals: Signals,
    valid_purchase_evidence: bool | None = True,
    needs_human_review: bool = False,
) -> tuple[int, str, str]:
    """Legacy tuple/lowercase interface with its existing trusted-evidence default.

    Pipeline callers already pass evidence validity explicitly. New callers
    should use calculate_score(), whose omitted evidence is treated as unknown.
    """
    value, decision, reason = _score(signals, valid_purchase_evidence, needs_human_review)
    return value, decision.value.lower(), reason
