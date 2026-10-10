"""Private draft schema and local grounding checks; public contracts stay frozen."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.contracts import ProductInput
from app.agents.reply_plan import ReplyPlan
from app.agents.screening import INSTRUCTION_PATTERNS, normalize


class ReplyPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["product_fact", "request_acknowledgement", "question"]
    text: str = Field(min_length=1, max_length=600)
    product_field: Literal["name", "description", "target_customer"] | None


class ReplyDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[ReplyPart] = Field(min_length=1, max_length=3)


# Free-form questions must not introduce sensitive commercial claims, calls to
# action, identifiers or instructions. Facts use exact Product text instead.
UNSAFE_QUESTION = re.compile(
    r"https?://|www\.|\b[\w-]+\.(?:com|org|net|io)\b|@|\d|[$€£]|"
    r"\b(?:price|costs?|discount|free|guarantee\w*|promise\w*|available|availability|"
    r"in stock|includes?|offers?|provides?|supports?|certifi\w*|refund\w*|"
    r"buy now|sign up|register now|approved|sent|booked|scheduled|appointment|tomorrow|ignore previous|instructions|"
    r"api[_ ]?key|system prompt|score|decision)\b|"
    r"قیمت|تخفیف|رایگان|تضمین|ضمانت|موجود|ظرفیت|گواهی|مدرک|رزرو|قطعی|فردا|"
    r"شامل|ارائه|پشتیبانی|تایید شد|تأیید شد|ارسال شد|دستور|کلید|امتیاز",
    re.IGNORECASE,
)
PERSIAN = re.compile(r"[\u0621-\u064a\u067e\u0686\u0698\u06a9\u06af\u06cc]")


def render_draft(draft: ReplyDraft, product: ProductInput, target_text: str, *, plan: ReplyPlan | None = None) -> str:
    """Allow exact Product facts, grounded request handling and a safe next step.

    Community claims are never product authority. These mechanical checks do not
    prove semantic safety of arbitrary language; every returned text is a draft.
    """
    questions = [part for part in draft.parts if part.kind == "question"]
    if len(questions) != 1 or draft.parts[-1].kind != "question":
        raise ValueError("Draft requires one final clarifying question")
    acknowledgements = [part for part in draft.parts if part.kind == "request_acknowledgement"]
    if plan and plan.acknowledgement:
        if (len(acknowledgements) != 1 or draft.parts[0] != acknowledgements[0]
                or acknowledgements[0].text != plan.acknowledgement
                or acknowledgements[0].product_field is not None):
            raise ValueError("Draft must address the actual commercial request with the exact safe acknowledgement")
        if plan.pricing_field and not any(part.kind == "product_fact" and part.product_field == plan.pricing_field for part in draft.parts):
            raise ValueError("Verified pricing acknowledgement requires its whole authoritative Product field")
    elif acknowledgements:
        raise ValueError("Unrequested or ungrounded acknowledgement")
    question = questions[0]
    planned_question = bool(plan and plan.next_question and question.text == plan.next_question)
    if plan and plan.next_question and not planned_question:
        raise ValueError("The next step must address the requested pricing or demo, not repeat known requirements")
    if plan and plan.customer_size_quote and re.search(r"how many (?:people|employees)|company size|team size|چند نفر|چند کارمند", normalize(question.text)):
        raise ValueError("Do not ask again for the customer's supplied company size")
    if (question.product_field is not None or not question.text.strip().endswith(("?", "؟"))
            or (not planned_question and UNSAFE_QUESTION.search(question.text))
            or re.search(r"[.!;\n]", question.text)
            or sum(question.text.count(char) for char in ("?", "؟")) != 1):
        raise ValueError("Unsafe draft question")
    persian = plan.language == "fa" if plan else bool(PERSIAN.search(target_text))
    if bool(PERSIAN.search(question.text)) != persian:
        raise ValueError("Draft question must match the target language")
    for part in draft.parts:
        if not part.text.strip() or any(ord(char) < 32 and char not in "\n\t" for char in part.text):
            raise ValueError("Invalid draft text")
        if any(re.search(pattern, normalize(part.text)) for pattern in INSTRUCTION_PATTERNS):
            raise ValueError("Untrusted instructions cannot become reply content")
        if part.kind == "product_fact":
            if part.product_field is None or part.text != getattr(product, part.product_field):
                # Substring matching alone would allow dropping negation or
                # qualifications, e.g. 'not available' -> 'available'.
                raise ValueError("Product claims must quote the whole supplied field exactly")
            # Do not repeat instructions disguised as a supplied product fact.
            if re.search(r"ignore previous|system prompt|api[_ ]?key|دستور|کلید", part.text, re.I):
                raise ValueError("Untrusted instructions cannot become reply facts")
            if bool(PERSIAN.search(part.text)) != persian:
                raise ValueError("Omit product quotes in another language")
    return " ".join(part.text.strip() for part in draft.parts)
