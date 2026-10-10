"""Deterministic reply planning, not qualification or sales scoring."""
from dataclasses import dataclass
import re
from typing import Literal

from app.agents.contracts import AgentInput, QualificationResult
from app.agents.screening import INSTRUCTION_PATTERNS, normalize

ReplyLanguage = Literal["en", "fa"]
PERSIAN_LETTERS = re.compile(r"[\u0621-\u064a\u067e\u0686\u0698\u06a9\u06af\u06cc]")
REQUEST_PATTERNS = {
    "pricing": r"\b(?:price|pricing|costs?|quote|how much)\b|قیمت|هزینه|چقدر",
    "demo": r"\b(?:demo|demonstration|walkthrough)\b|دمو|نمایش آزمایشی|نمایش محصول",
    "integration": r"\b(?:integrat\w*|connect\w*|api)\b|یکپارچه|اتصال|وصل",
    "comparison": r"\b(?:compar\w*|versus|vs\.?|alternative\w*)\b|مقایسه|جایگزین",
    "follow_up": r"\b(?:follow up|following up|any update|heard back)\b|پیگیری|خبر جدید",
    "objection": r"\b(?:expensive|not sure|concern\w*|but|uncertain)\b|گران|گرونه|مطمئن نیست|نگران",
    "product_question": r"\b(?:does|can|supports?|features?|suitable)\b|قابلیت|مناسب|پشتیبانی",
}


@dataclass(frozen=True)
class ReplyPlan:
    language: ReplyLanguage
    requests: tuple[str, ...]
    acknowledgement: str | None
    next_question: str | None
    customer_size_quote: str | None
    pricing_field: str | None

    def model_payload(self) -> dict:
        return {"language": self.language, "requests": list(self.requests),
                "required_acknowledgement": self.acknowledgement,
                "suggested_next_question": self.next_question,
                "customer_size_quote": self.customer_size_quote, "pricing_field": self.pricing_field}


def _safe_text(text: str) -> str:
    text = normalize(text)
    for pattern in INSTRUCTION_PATTERNS:
        text = re.sub(pattern, " ", text)
    return text


def plan_reply(inputs: AgentInput, qualification: QualificationResult,
               language: ReplyLanguage | None = None) -> ReplyPlan:
    """Prioritize the target and the same author's supplied conversation context.

    A quoted customer's request remains data, never a product claim. No inferred
    availability, pricing, appointments or capabilities are added to the plan.
    Language is selected only by the target or an explicit caller override.
    """
    if language is not None and language not in ("en", "fa"):
        raise ValueError("Reply language must be en or fa")
    language = language or ("fa" if PERSIAN_LETTERS.search(inputs.message.content) else "en")
    texts = [inputs.message.content, *(message.content for message in inputs.context_messages
                                     if message.author == inputs.message.author)]
    combined = " ".join(_safe_text(text) for text in texts)
    requests = tuple(name for name, pattern in REQUEST_PATTERNS.items() if re.search(pattern, combined))
    price, demo = "pricing" in requests, "demo" in requests
    acknowledgement = next_question = None
    pricing_field = None
    for field in (("description", "name") if price else ()):
        value = getattr(inputs.product, field)
        if (len(value) <= 600 and bool(PERSIAN_LETTERS.search(value)) == (language == "fa")
                and re.search(REQUEST_PATTERNS["pricing"], normalize(value))
                and re.search(r"[$€£]|\b(?:USD|EUR|GBP)\b|تومان|ریال", value, re.I)
                and re.search(r"[0-9۰-۹]", value)
                and not any(re.search(pattern, normalize(value)) for pattern in INSTRUCTION_PATTERNS)):
            pricing_field = field
            break
    if language == "en":
        if price and demo:
            acknowledgement = "Thanks for asking about pricing and a demo. I don't have verified pricing to share here."
            next_question = "Would you like to confirm pricing and discuss the next steps for a demo?"
        elif price:
            acknowledgement = "Thanks for asking about pricing. I don't have a verified price to share here."
            next_question = "Would you like to confirm the pricing options?"
        elif demo:
            acknowledgement = "Thanks for requesting a demo."
            next_question = "Do you have a preferred time for a demo discussion?"
    else:
        if price and demo:
            acknowledgement = "ممنون از درخواست قیمت و دمو. قیمت تأییدشده‌ای در اطلاعات موجود ندارم."
            next_question = "مایلید ابتدا قیمت بررسی شود یا دربارهٔ مراحل هماهنگی دمو صحبت کنیم؟"
        elif price:
            acknowledgement = "ممنون از پرسش درباره قیمت. در اطلاعات موجود قیمت تأییدشده‌ای ندارم."
            next_question = "مایلید گزینه‌های قیمت بررسی شود؟"
        elif demo:
            acknowledgement = "ممنون از درخواست دمو."
            next_question = "برای گفتگو دربارهٔ دمو چه زمانی را ترجیح می‌دهید؟"
    if price and pricing_field:
        acknowledgement = (
            "Thanks for asking about pricing. The supplied pricing information is quoted below."
            if language == "en" else "ممنون از پرسش درباره قیمت. اطلاعات قیمت موجود در ادامه نقل شده است.")
        if demo:
            acknowledgement += (" Thanks for requesting a demo as well." if language == "en"
                                else " ممنون از درخواست دمو هم.")
    # Retain an exact customer quote rather than turning company size into an
    # assertion about product suitability or account terms.
    size = None
    for text in texts:
        match = re.search(r"\b\d{1,5}[- ](?:person|employee|people)\b|\b\d{1,5}\s+employees\b|[0-9۰-۹]{1,5}\s*(?:نفر|کارمند)", text, re.I)
        if match:
            size = match.group(0)
            break
    return ReplyPlan(language, requests, acknowledgement, next_question, size, pricing_field)