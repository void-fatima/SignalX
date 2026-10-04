from math import floor
from app.agents.contracts import Signals

SCORING_VERSION = "score_v1"
WEIGHTS = {"purchase_intent": 30, "product_fit": 30, "need_strength": 15,
           "urgency": 10, "confidence": 10, "response_opportunity": 5}


def score(signals: Signals, valid_purchase_evidence: bool = True, needs_human_review: bool = False) -> tuple[int, str, str]:
    signals = Signals.model_validate(signals.model_dump())
    value = max(0, min(100, floor(sum(weight * getattr(signals, name) for name, weight in WEIGHTS.items()) + 0.5)))
    decision = "respond" if value >= 70 else "review" if value >= 40 else "ignore"
    reason = "score_threshold_met"
    if decision == "respond":
        for condition, why in [(signals.confidence < .60, "low_confidence"), (signals.product_fit < .50, "low_product_fit"), (not valid_purchase_evidence, "invalid_purchase_evidence"), (needs_human_review, "human_review_required")]:
            if condition:
                decision, reason = "review", why
                break
    return value, decision, reason
