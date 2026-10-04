import re
from app.agents.contracts import ProductSnapshot, TargetMessage, ScreeningResult


def normalize(text: str) -> str:
    return " ".join(text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").lower().split())


STOP_WORDS = {"this", "that", "with", "from", "your", "have", "will", "through", "based", "برای", "است", "های", "شده"}


def words(text: str) -> set[str]:
    return set(re.findall(r"\w+", normalize(text)))


def related(text: str, product: ProductSnapshot) -> bool:
    tokens = words(" ".join([product.name, product.description, *product.problems_solved, *product.best_fit]))
    terms = {t for t in tokens if len(t) >= 3 and t not in STOP_WORDS}
    return bool(terms & words(text))


def screen(product: ProductSnapshot, target: TargetMessage, context: list[TargetMessage]) -> ScreeningResult:
    if related(target.content, product):
        return ScreeningResult(is_candidate=True, reason="explicit_need")
    # Defend this public Agent function even when called outside the pipeline.
    context = [m for m in context if m.conversation_id == target.conversation_id and m.id != target.id]
    prior = sorted((m for m in context if (m.timestamp, m.external_id) < (target.timestamp, target.external_id)), key=lambda m: (m.timestamp, m.external_id))[-3:]
    if target.reply_to_external_id or any(related(m.content, product) for m in prior):
        return ScreeningResult(is_candidate=True, reason="conversation_dependency")
    if words(target.content) & {"آره", "گرونه", "این", "همون", "it", "that", "expensive", "شاید", "maybe"}:
        return ScreeningResult(is_candidate=True, reason="ambiguous_reference")
    return ScreeningResult(is_candidate=False, reason="no_product_or_context_signal")
