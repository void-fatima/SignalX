"""Private draft schema and local grounding checks; public contracts stay frozen."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.contracts import ProductInput
from app.agents.screening import INSTRUCTION_PATTERNS, normalize


class ReplyPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["product_fact", "question"]
    text: str = Field(min_length=1, max_length=600)
    product_field: Literal["name", "description", "target_customer"] | None


class ReplyDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[ReplyPart] = Field(min_length=1, max_length=3)


class ReplyValidationError(ValueError):
    """Name the existing policy check without exposing the rejected text."""
    def __init__(self, failed_check: str, message: str):
        super().__init__(message)
        self.failed_check = failed_check


# Free-form questions must not introduce sensitive commercial claims, calls to
# action, identifiers or instructions. Facts use exact Product text instead.
UNSAFE_QUESTION = re.compile(
    r"https?://|www\.|\b[\w-]+\.(?:com|org|net|io)\b|@|\d|[$€£]|"
    r"\b(?:price|costs?|discount|free|guarantee\w*|promise\w*|available|availability|"
    r"in stock|includes?|offers?|provides?|supports?|certifi\w*|refund\w*|"
    r"buy now|sign up|register now|approved|sent|ignore previous|instructions|"
    r"api[_ ]?key|system prompt|score|decision)\b|"
    r"قیمت|تخفیف|رایگان|تضمین|ضمانت|موجود|ظرفیت|گواهی|مدرک|"
    r"شامل|ارائه|پشتیبانی|تایید شد|تأیید شد|ارسال شد|دستور|کلید|امتیاز",
    re.IGNORECASE,
)
PERSIAN = re.compile(r"[\u0621-\u064a\u067e\u0686\u0698\u06a9\u06af\u06cc]")


def render_draft(draft: ReplyDraft, product: ProductInput, target_text: str) -> str:
    """Only whole Product fields and a cautious clarifying question are allowed.

    Community claims are never product authority. These mechanical checks do not
    prove semantic safety of arbitrary language; every returned text is a draft.
    """
    questions = [part for part in draft.parts if part.kind == "question"]
    if len(questions) != 1 or draft.parts[-1].kind != "question":
        raise ReplyValidationError("reply_question_structure", "Draft requires one final clarifying question")
    question = questions[0]
    if (question.product_field is not None or not question.text.strip().endswith(("?", "؟"))
            or UNSAFE_QUESTION.search(question.text)
            or re.search(r"[.!;\n]", question.text)
            or sum(question.text.count(char) for char in ("?", "؟")) != 1):
        raise ReplyValidationError("reply_question_safety", "Unsafe draft question")
    if bool(PERSIAN.search(question.text)) != bool(PERSIAN.search(target_text)):
        raise ReplyValidationError("reply_question_language", "Draft question must match the target language")
    for part in draft.parts:
        if not part.text.strip() or any(ord(char) < 32 and char not in "\n\t" for char in part.text):
            raise ReplyValidationError("reply_text_content", "Invalid draft text")
        if any(re.search(pattern, normalize(part.text)) for pattern in INSTRUCTION_PATTERNS):
            raise ReplyValidationError("reply_untrusted_instruction", "Untrusted instructions cannot become reply content")
        if part.kind == "product_fact":
            if part.product_field is None or part.text != getattr(product, part.product_field):
                # Substring matching alone would allow dropping negation or
                # qualifications, e.g. 'not available' -> 'available'.
                raise ReplyValidationError("reply_product_fact_grounding", "Product claims must quote the whole supplied field exactly")
            # Do not repeat instructions disguised as a supplied product fact.
            if re.search(r"ignore previous|system prompt|api[_ ]?key|دستور|کلید", part.text, re.I):
                raise ReplyValidationError("reply_product_fact_instruction", "Untrusted instructions cannot become reply facts")
            if bool(PERSIAN.search(part.text)) != bool(PERSIAN.search(target_text)):
                raise ReplyValidationError("reply_product_fact_language", "Omit product quotes in another language")
    return " ".join(part.text.strip() for part in draft.parts)
