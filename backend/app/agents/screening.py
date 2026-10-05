"""Deterministic, high-recall pre-filter. No qualification or provider calls."""
import re
import unicodedata
from app.agents.contracts import ProductSnapshot, TargetMessage, ScreeningResult


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").replace("’", "'")
    return " ".join(normalized.split())


STOP_WORDS = {
    "the", "and", "for", "are", "was", "you", "our", "can", "this", "that", "with",
    "from", "your", "have", "will", "through", "based", "any", "who", "its", "into",
    "برای", "است", "های", "شده", "این", "آن", "یک", "هایشان", "هست", "بود",
}

# Recognized instruction phrases are never positive screening signals. Removing
# them from lexical checks is a small deterministic safeguard, not an LLM defense.
INSTRUCTION_PATTERNS = (
    r"\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b",
    r"\bset\s+my\s+score\s+(?:to\s+)?\d+\b",
    r"\bmark\s+(?:this(?:\s+message)?|me)\s+as\s+(?:a\s+)?lead\b",
    r"دستورهای قبلی را نادیده بگیر",
    r"امتیاز (?:مرا|من را)\s+\d+\s*(?:بده|قرار بده)",
    r"این (?:پیام را )?(?:به عنوان )?لید (?:ثبت|علامت گذاری) کن",
)
DIRECT_SIGNAL = re.compile(
    r"\b(?:looking\s+for|searching\s+for|need|needs|want|wants|buy|buying|purchase|"
    r"register|registration|recommend|recommendation|enroll|sign\s+up|"
    r"how\s+much|price|pricing|cost|costs|available|availability|in\s+stock|"
    r"suitable|for\s+beginners|where\s+can\s+i\s+get)\b"
    r"|\b(?:دنبال|نیاز|می خواهم|می خوام|میخوام|میخواهم|خرید|ثبت نام|"
    r"پیشنهاد|توصیه|قیمت|هزینه|چقدر|موجود|مناسب|مناسبه|مبتدی|از کجا)\b"
)
NOISE_TOPICS = {
    "football", "soccer", "basketball", "sports", "politics", "coffee", "weather",
    "فوتبال", "بسکتبال", "ورزش", "پیاده", "هوا", "قهوه",
}
NOISE_CHATTER = {
    "match", "game", "won", "win", "tonight", "today", "afternoon", "great", "nice",
    "بازی", "نتیجه", "امروز", "عالیه", "پیاده روی",
}
SOCIAL_ONLY = {
    "hi", "hello", "hey", "good morning", "good night", "thanks", "thank you",
    "lol", "haha", "hahaha", "bye", "سلام", "درود", "صبح بخیر", "شب بخیر",
    "ممنون", "مرسی", "خداحافظ", "چه خبر",
}
REFERENCES = {"yes", "yeah", "maybe", "it", "that", "expensive", "good", "beginners",
              "آره", "بله", "شاید", "گرونه", "این", "همون", "خوبه"}


def _message_data(text: str) -> str:
    data = normalize(text)
    for pattern in INSTRUCTION_PATTERNS:
        data = re.sub(pattern, " ", data)
    return " ".join(data.split())


def words(text: str) -> set[str]:
    return set(re.findall(r"\w+", normalize(text)))


def related(text: str, product: ProductSnapshot) -> bool:
    """Lexical relevance only, not product fit or personal purchase intent."""
    tokens = words(" ".join([product.name, product.description, product.target_customer,
                             *product.problems_solved, *product.best_fit]))
    terms = {t for t in tokens if len(t) >= 3 and t not in STOP_WORDS}
    return bool(terms & words(_message_data(text)))


def screen(product: ProductSnapshot, target: TargetMessage, context: list[TargetMessage]) -> ScreeningResult:
    """Reject only recognizable noise; retain uncertainty for later qualification.

    Context is selected/bounded by the caller. Supplied offline following messages
    may establish relevance too. A reply ID alone is not evidence of relevance.
    """
    data = _message_data(target.content)
    target_words = words(data)
    if not any(character.isalpha() for character in data):
        return ScreeningResult(is_candidate=False, reason="empty_or_meaningless")
    if related(data, product):
        return ScreeningResult(is_candidate=True, reason="product_or_problem_reference")
    if DIRECT_SIGNAL.search(data):
        return ScreeningResult(is_candidate=True, reason="direct_signal")
    # A clear unrelated topic does not become relevant merely because product
    # discussion happens nearby. Direct/relevant signals above take precedence.
    if target_words & NOISE_TOPICS and target_words & NOISE_CHATTER:
        return ScreeningResult(is_candidate=False, reason="unrelated_conversation_noise")
    # Defend this public Agent function even when called outside the pipeline.
    context = [m for m in context if m.conversation_id == target.conversation_id and m.id != target.id]
    if any(related(m.content, product) for m in context):
        return ScreeningResult(is_candidate=True, reason="conversation_dependency")
    social_text = " ".join(re.findall(r"\w+", data))
    if social_text in SOCIAL_ONLY:
        return ScreeningResult(is_candidate=False, reason="greeting_or_social_noise")
    if target_words & REFERENCES:
        return ScreeningResult(is_candidate=True, reason="ambiguous_reference")
    return ScreeningResult(is_candidate=True, reason="uncertain_keep_for_qualification")
