"""Deterministic qualification and grounded evidence; no scoring or provider calls."""
import re
from pydantic import ValidationError
from app.agents.contracts import (
    ContextMessage, Evidence, EvidenceItem, MessageInput, ProductInput, ProductSnapshot,
    Qualification, QualificationResult, Signals, TargetMessage, UsageEvent,
)
from app.agents.providers.base import ProviderError
from app.agents.screening import INSTRUCTION_PATTERNS, STOP_WORDS, normalize, words


SEARCH = re.compile(r"\b(?:looking for|searching for|need|want to buy|buy|buying|purchase|register|enroll|where can i get)\b|دنبال|نیاز|می خوام|میخوام|می خواهم|خرید|ثبت نام|از کجا")
RECOMMEND = re.compile(r"\b(?:recommend|recommendation|suggest)\b|پیشنهاد|معرفی|توصیه")
PRICE = re.compile(r"\b(?:price|pricing|how much|cost|costs)\b|قیمت|هزینه|چقدر")
AVAILABLE = re.compile(r"\b(?:available|availability|in stock)\b|موجود|ظرفیت")
COMPARE = re.compile(r"\b(?:compare|comparing|versus|better than|which option)\b|مقایسه|کدام بهتر|کدوم بهتر")
TECHNICAL = re.compile(r"\b(?:error|traceback|debug|how do i fix|how does|how to fix)\b|خطا|ارور|چطور رفع|چگونه رفع")
OBJECTION = re.compile(r"\b(?:expensive|too costly|cannot afford|can't afford)\b|گرونه|گران|گرانه")
URGENT = re.compile(r"\b(?:now|today|asap|urgently|urgent|immediately)\b|همین الان|همین حالا|امروز|فوری|هرچه زودتر")
NOT_URGENT = re.compile(r"\b(?:not urgent|no rush|not today|not now|not immediately)\b|عجله ندارم|فوری نیست|امروز لازم نیست")
HYPOTHETICAL = re.compile(r"\b(?:maybe|perhaps|hypothetically|someday|if i)\b|شاید|فرض|احتمالا")
NEGATIVE = re.compile(r"\b(?:not buying|don't want|do not want|no need|not interested|not suitable|unsuitable|not for)\b|نمی خوام|نمیخوام|قصد خرید ندارم|مناسب نیست|نیاز ندارم")
THIRD_PARTY = re.compile(r"\b(?:my friend|my colleague|someone else|he needs|she needs|they need)\b|دوستم|همکارم|او نیاز|اون نیاز")
INSTRUCTIONS = (*INSTRUCTION_PATTERNS,
    r"\bset\s+my\s+(?:product_fit|purchase_intent|need_strength|urgency|confidence|response_opportunity)\s+to\s+[\d.]+",
)
QUOTES = re.compile(r'"[^"\n]*"|“[^”\n]*”|«[^»\n]*»')


def _data(text: str) -> str:
    data = normalize(text)
    for pattern in INSTRUCTIONS:
        data = re.sub(pattern, " ", data)
    return " ".join(data.split())


def _personal_text(text: str) -> tuple[str, bool]:
    data = _data(text)
    quoted = bool(QUOTES.search(data) or THIRD_PARTY.search(data))
    data = QUOTES.sub(" ", data)
    # Conservatively exclude third-party sentences; retain separate first-person sentences.
    sentences = re.split(r"[.!?؟;\n]+", data)
    return " ".join(s.strip() for s in sentences if not THIRD_PARTY.search(s)).strip(), quoted


def _terms(text: str) -> set[str]:
    return {w for w in words(text) if len(w) >= 3 and w not in STOP_WORDS}


def _profile_terms(product: ProductSnapshot | ProductInput) -> set[str]:
    return _terms(" ".join([product.name, product.description, product.target_customer,
        *getattr(product, "problems_solved", []), *getattr(product, "best_fit", [])]))


def _relevant(text: str, product: ProductSnapshot | ProductInput) -> bool:
    return bool(_terms(_data(text)) & _profile_terms(product))


def qualify(
    product: ProductSnapshot | ProductInput,
    target: TargetMessage | MessageInput,
    context: list[TargetMessage | ContextMessage],
) -> QualificationResult:
    """Return heuristic signals, never a final score or decision.

    ContextMessage has no conversation field: its caller must supply scoped context.
    Legacy TargetMessage context is additionally checked here. Signals are initial
    rule estimates, not measured probabilities or model accuracy.
    """
    scoped = [m for m in context if m.id != target.id
        and getattr(m, "conversation_id", target.conversation_id) == target.conversation_id]
    if len({m.id for m in scoped}) != len(scoped):
        raise ValueError("Context message IDs must be unique")
    scoped = sorted(scoped, key=lambda m: (m.timestamp, m.id))
    relevant = [m for m in scoped if _relevant(m.content, product)]
    personal, quoted = _personal_text(target.content)
    target_related = _relevant(personal, product)
    contextual = bool(relevant) and not target_related
    negative = bool(NEGATIVE.search(personal))
    hypothetical = bool(HYPOTHETICAL.search(personal))
    intent = "uncertain"
    if TECHNICAL.search(personal):
        intent = "technical_help"
    elif OBJECTION.search(personal):
        intent = "objection"
    elif AVAILABLE.search(personal):
        intent = "asking_availability"
    elif PRICE.search(personal):
        intent = "asking_price"
    elif COMPARE.search(personal):
        intent = "comparing_options"
    elif RECOMMEND.search(personal):
        intent = "asking_recommendation"
    elif SEARCH.search(personal):
        intent = "searching_for_course" if re.search(r"\bcourse\b|دوره", normalize(product.name + " " + product.description)) else "searching_for_product"
    action = intent.startswith("searching_for_")
    values = {
        "searching_for_course": (.9, .85, .9), "searching_for_product": (.9, .85, .9),
        "asking_recommendation": (.65, .65, .95), "asking_price": (.65, .55, .9),
        "asking_availability": (.75, .65, .9), "comparing_options": (.55, .5, .8),
        "technical_help": (.1, .55, .65), "objection": (.45, .45, .7),
        "uncertain": (.15, .2, .3),
    }
    purchase, strength, opportunity = values[intent]
    # Name mention alone is weak evidence of fit. Multiple profile terms or an
    # explicit need overlapping problem/audience/best-fit supply stronger support.
    matched = _terms(personal) & _profile_terms(product)
    non_name = matched - _terms(product.name)
    fit = .85 if target_related and non_name and (len(matched) >= 2 or action) else .45 if target_related else .15
    if contextual and intent in {"objection", "asking_price", "asking_availability", "uncertain"}:
        fit = .65
    confidence = .8 if intent != "uncertain" and target_related else .65 if contextual and intent != "uncertain" else .4
    limitations = ["Deterministic heuristic signals; not calibrated probabilities", "Budget is unknown"]
    urgency = .85 if URGENT.search(personal) and not NOT_URGENT.search(personal) else 0.0
    if urgency == 0:
        limitations.append("No explicit urgency in the target author's message")
    if not target_related and not relevant:
        limitations.append("No relevant product context; fit is weak or uncertain")
    if intent == "uncertain":
        limitations.append("The author's need or intent is unclear; human review required")
    if quoted:
        limitations.append("Quoted or third-party needs are not attributed to the author")
        confidence = min(confidence, .45)
        if not SEARCH.search(personal) and intent == "uncertain":
            purchase, strength, urgency = .1, .15, 0.0
    if hypothetical:
        purchase, strength, confidence = min(purchase, .35), min(strength, .35), min(confidence, .45)
        limitations.append("Hypothetical or tentative need; human review required")
    if negative:
        purchase, strength, confidence = .05, min(strength, .2), min(confidence, .55)
        limitations.append("Target contains negative or conflicting purchase signals")
    excluded = _terms(" ".join(getattr(product, "not_fit", []))) & _terms(personal)
    if excluded:
        fit, confidence = min(fit, .25), min(confidence, .5)
        limitations.append("Target overlaps the product's not_fit profile")
    conflicting = [m for m in relevant if NEGATIVE.search(_data(m.content))]
    if conflicting:
        confidence, fit = min(confidence, .5), min(fit, .45)
        limitations.append("Relevant context contains conflicting suitability or purchase signals")
    needs = {
        "asking_price": "Wants pricing information", "asking_availability": "Wants availability information",
        "asking_recommendation": "Seeks a recommendation", "comparing_options": "Wants to compare options",
        "technical_help": "Seeks technical help; purchase intent is not established",
        "objection": "Raises a price objection; purchase commitment is uncertain",
        "uncertain": "Need is unclear; further clarification is required",
    }
    need = ("Expresses a search or need: " + personal[:160]) if action else needs[intent]
    evidence = []
    # Original text is quoted, never normalized or paraphrased as evidence.
    if target.content.strip() and _data(target.content).strip(" .!?؟;"):
        evidence.append(EvidenceItem(message_id=target.id, quote=target.content,
            reason="Target text supports the stated intent or its uncertainty; quoted needs may belong to others"))
    for m in relevant:
        if contextual or m in conflicting:
            evidence.append(EvidenceItem(message_id=m.id, quote=m.content,
                reason="Same-conversation product context" if m not in conflicting else "Conflicting same-conversation context"))
    return QualificationResult(intent=intent, need=need, purchase_intent=purchase,
        product_fit=fit, need_strength=strength, urgency=urgency, confidence=confidence,
        response_opportunity=opportunity, evidence=evidence, limitations=limitations)


def qualify_legacy(product: ProductSnapshot, target: TargetMessage, context: list[TargetMessage]) -> Qualification:
    """Adapter for legacy callers; no provider usage or final score is produced."""
    result = qualify(product, target, context)
    return Qualification(signals=Signals(**{name: getattr(result, name) for name in Signals.model_fields}),
        intent=result.intent, need=result.need, reason=result.need, budget_signal="unknown",
        evidence=[Evidence(message_id=e.message_id, quote=e.quote) for e in result.evidence],
        limitations=result.limitations, needs_human_review=result.confidence < .6)


def validate_qualification(
    output: Qualification,
    target: TargetMessage,
    context: list[TargetMessage],
    usage: list[UsageEvent],
) -> tuple[Qualification, bool]:
    try:
        # Revalidate serialized models too: model_copy/mutation can bypass validation.
        qualification = Qualification.model_validate(output.model_dump())
    except (ValidationError, AttributeError) as exc:
        raise ProviderError("Provider returned invalid qualification signals", usage) from exc
    allowed = {m.id: m.content for m in [target, *context]}
    if any(e.message_id not in allowed or not e.quote.strip() or e.quote not in allowed[e.message_id]
           for e in qualification.evidence):
        raise ProviderError("Provider evidence is not grounded in supplied messages", usage)
    target_evidence = any(e.message_id == target.id for e in qualification.evidence)
    return qualification, target_evidence
