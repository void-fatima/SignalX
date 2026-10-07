"""Private, content-free Gemini reply parsing and validation diagnostics."""
import json
from copy import deepcopy

from pydantic import ValidationError

from app.agents.reply_draft import ReplyValidationError

EXPECTED_SHAPE = {
    "type": "object", "required_fields": ["parts"], "additional_fields_allowed": False,
    "parts": {"type": "array", "min_items": 1, "max_items": 3,
        "item_required_fields": ["kind", "text", "product_field"],
        "kind": ["question", "product_fact"], "text": "nonempty string; at most 600 characters",
        "product_field": ["name", "description", "target_customer", None]},
    "policy": "one final question in target language; facts must equal whole Product fields",
}

CHECKS = {
    "reply_response_json": ("parsing", "The HTTP response body is not valid JSON."),
    "reply_response_object": ("provider_envelope", "The Chat Completions response body must be an object."),
    "reply_choices": ("provider_envelope", "Exactly one Chat Completions choice is required."),
    "reply_choice_object": ("provider_envelope", "The completion choice must be an object."),
    "reply_message_object": ("provider_envelope", "The completion message must be an object."),
    "reply_completion": ("provider_envelope", "An assistant completion with stop finish reason and no tools is required."),
    "reply_content_string": ("provider_envelope", "The assistant content must be a JSON string containing an object."),
    "reply_json": ("parsing", "The assistant content is not valid JSON."),
    "reply_markdown_fence": ("parsing", "Markdown-fenced output is rejected; only the JSON object is accepted."),
    "reply_top_level_object": ("output_shape", "The parsed reply must be an object with parts, not plain text or an array."),
    "reply_secret_echo": ("security", "A secret echo prevents accepting the reply."),
    "reply_pydantic_schema": ("pydantic_validation", "The parts object failed strict local ReplyDraft validation."),
    "reply_question_structure": ("reply_policy", "Exactly one final clarifying question is required."),
    "reply_question_safety": ("reply_policy", "The question violates punctuation, commercial-claim or instruction restrictions."),
    "reply_question_language": ("reply_language", "The question must match the target language, regardless of metadata language."),
    "reply_text_content": ("reply_policy", "A reply part is blank or contains disallowed control characters."),
    "reply_untrusted_instruction": ("security", "Untrusted instructions cannot be repeated as reply content."),
    "reply_product_fact_grounding": ("grounding", "A fact must equal its complete supplied Product field; translation/paraphrase is rejected."),
    "reply_product_fact_instruction": ("security", "Instructions cannot be repeated as Product facts."),
    "reply_product_fact_language": ("reply_language", "Product facts in another language must be omitted, not translated."),
    "reply_refused": ("provider_envelope", "The provider refused generation."),
    "reply_truncated": ("provider_envelope", "The provider truncated generation."),
    "reply_local_validation": ("local_validation", "The reply failed a local validation check."),
}

# Never report unknown property names, literal values, error inputs/context or
# raw exception messages. A malicious field name itself can contain a secret.
KNOWN_FIELDS = {"parts", "kind", "text", "product_field", "suggested_reply", "response_text", "reply",
                "choices", "message", "content", "role", "finish_reason", "evidence", "score", "decision"}
ERROR_TYPES = {"missing", "extra_forbidden", "string_type", "string_too_short", "string_too_long",
               "literal_error", "list_type", "too_short", "too_long", "model_type", "dict_type"}


def output_shape(value: object, depth: int = 0) -> dict[str, object]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, dict):
        result = {"type": "object", "unknown_field_count": sum(name not in KNOWN_FIELDS for name in value)}
        if depth < 3:
            result["fields"] = {name: output_shape(value[name], depth + 1)
                                for name in sorted(KNOWN_FIELDS.intersection(value))}
        return result
    if isinstance(value, list):
        return {"type": "array", "item_count": len(value),
                "items": [output_shape(item, depth + 1) for item in value[:3]] if depth < 3 else []}
    if isinstance(value, str):
        return {"type": "string", "empty": not value.strip(),
                "format": "markdown_fenced" if value.lstrip().startswith("```") else "unspecified"}
    return {"type": "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "unknown"}


class ReplyOutputError(ValueError):
    def __init__(self, failed_check: str, observed: object, *, outcome: str = "invalid_output"):
        super().__init__(CHECKS[failed_check][1])
        self.failed_check = failed_check
        self.observed_shape = output_shape(observed)
        self.outcome = outcome


def parse_reply_completion(body: object, *, response_json_valid: bool) -> dict:
    """Same strict envelope/JSON requirements; never strip fences or coerce text."""
    if not response_json_valid:
        raise ReplyOutputError("reply_response_json", None)
    if not isinstance(body, dict):
        raise ReplyOutputError("reply_response_object", body)
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ReplyOutputError("reply_choices", choices)
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ReplyOutputError("reply_choice_object", choice)
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ReplyOutputError("reply_message_object", message)
    finish = choice.get("finish_reason")
    if message.get("refusal") or (isinstance(finish, str) and finish in {"content_filter", "safety"}):
        raise ReplyOutputError("reply_refused", message, outcome="refused")
    if finish == "length":
        raise ReplyOutputError("reply_truncated", message, outcome="incomplete")
    if (finish != "stop" or message.get("role") != "assistant"
            or message.get("tool_calls") or message.get("function_call")):
        raise ReplyOutputError("reply_completion", message)
    content = message.get("content")
    if not isinstance(content, str):
        raise ReplyOutputError("reply_content_string", content)
    try:
        payload = json.loads(content)
    except (ValueError, RecursionError):
        check = "reply_markdown_fence" if content.lstrip().startswith("```") else "reply_json"
        raise ReplyOutputError(check, content) from None
    if not isinstance(payload, dict):
        raise ReplyOutputError("reply_top_level_object", payload)
    return payload


def validation_diagnostic(exc: Exception, payload: object, stage: str, attempt: int) -> dict[str, object]:
    if isinstance(exc, ReplyOutputError):
        check, shape = exc.failed_check, exc.observed_shape
    else:
        check = ("reply_pydantic_schema" if isinstance(exc, ValidationError) else
                 exc.failed_check if isinstance(exc, ReplyValidationError) and exc.failed_check in CHECKS else
                 "reply_local_validation")
        shape = output_shape(payload)
    category, explanation = CHECKS[check]
    diagnostic = {"stage": stage, "attempt_no": attempt, "failed_check": check,
        "failure_category": category, "explanation": explanation,
        "expected_output_shape": deepcopy(EXPECTED_SHAPE), "observed_output_shape": shape,
        "parsing_failed": category == "parsing", "pydantic_validation_failed": isinstance(exc, ValidationError)}
    if isinstance(exc, ValidationError):
        diagnostic["schema_errors"] = [{"location": [part if type(part) is int or part in {"parts", "kind", "text", "product_field"}
                                                      else "[extra]" for part in error["loc"]],
            "type": error["type"] if error["type"] in ERROR_TYPES else "validation_error"}
            for error in exc.errors(include_url=False, include_input=False, include_context=False)[:12]]
    return diagnostic
