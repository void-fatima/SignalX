"""OpenAI Responses qualification and explicit drafts; no persistence or fallback."""
import json
import os
from contextlib import nullcontext
from time import perf_counter

import httpx
from pydantic import SecretStr, ValidationError

from app.agents.contracts import (
    AgentInput, AgentOutput, Decision, Evidence, ProductSnapshot, Qualification,
    QualificationResult, Signals, TargetMessage, UsageEvent, UsageInfo,
)
from app.agents.cost import calculate_cost
from app.agents.prompts.qualification import PROMPT_VERSION, build_messages, output_schema
from app.agents.prompts.reply import build_reply_messages, output_schema as reply_schema
from app.agents.providers.base import BaseProvider, ProviderError
from app.agents.providers.config import RealProviderConfig
from app.agents.qualification import validate_qualification_result
from app.agents.screening import screen
from app.agents.scoring import screening_decision_reason
from app.agents.reply_draft import ReplyDraft, render_draft
from app.agents.reply_plan import ReplyLanguage, plan_reply


def _legacy_result(result: QualificationResult) -> Qualification:
    return Qualification(intent=result.intent, need=result.need, reason=result.need,
        signals=Signals(**{name: getattr(result, name) for name in Signals.model_fields}),
        evidence=[Evidence(message_id=e.message_id, quote=e.quote) for e in result.evidence],
        limitations=result.limitations, needs_human_review=result.confidence < .6)


def _legacy_usage(records: list[UsageInfo]) -> list[UsageEvent]:
    return [UsageEvent(stage=r.stage, attempt_no=r.attempt_no, provider_mode="real",
        model=r.model, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
        cost_usd=str(r.estimated_cost) if r.estimated_cost is not None else None,
        cost_status=r.cost_status, price_version=r.price_version or "unknown",
        latency_ms=r.latency_ms, outcome=r.outcome) for r in records]


def _tokens(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _http_failure(status_code: int, body: dict) -> str:
    """Expose status and fixed diagnoses, never untrusted API error messages."""
    error = body.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str) and code in {"model_not_found", "model_not_available", "unsupported_model", "model_not_supported"}:
        diagnosis = "selected model unavailable or inaccessible"
    elif isinstance(code, str) and code in {"invalid_json_schema", "unsupported_parameter", "unsupported_value"}:
        diagnosis = "model/request incompatible with Responses structured output parameters"
    else:
        diagnosis = {400: "invalid or unsupported model/request parameters",
            401: "authentication failed", 403: "access denied", 404: "endpoint or model unavailable",
            429: "rate limit or account quota exceeded"}.get(status_code, "provider request rejected")
    return f"Real provider returned an unsuccessful HTTP response (HTTP {status_code}: {diagnosis})"


class RealProvider(BaseProvider):
    provider_mode = "real"
    prompt_version = PROMPT_VERSION

    def __init__(self, config: RealProviderConfig | None = None, *, client: httpx.Client | None = None):
        self.config = config if config is not None else RealProviderConfig.from_env()
        self.config.require_valid()
        # Credentials have exactly one source, including when settings/client are injected.
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key or not key.isascii() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in key):
            raise ProviderError("Real provider is not configured: a valid OPENAI_API_KEY is required", [])
        self._api_key = SecretStr(key)
        # Injected clients are caller-owned. Production clients have no transport retries.
        self._client = client

    def _usage(self, body: dict, attempt: int, started: float, stage: str = "qualification") -> UsageInfo:
        usage = body.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        reported_model = body.get("model")
        model = reported_model if isinstance(reported_model, str) and reported_model.strip() else self.config.model
        input_tokens = _tokens(usage.get("input_tokens"))
        output_tokens = _tokens(usage.get("output_tokens"))
        rates = self.config.rates
        details = usage.get("input_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else None
        # Two-rate accounting cannot price cached input accurately. Keep cost unknown.
        if reported_model != self.config.model or _tokens(cached) != 0:
            rates = None
        cost = calculate_cost("real", input_tokens, output_tokens, rates)
        return UsageInfo(stage=stage if attempt == 1 else stage + "_repair",
            attempt_no=attempt, provider_mode="real", model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            estimated_cost=cost.cost_usd, cost_status=cost.cost_status,
            price_version=cost.price_version, latency_ms=max(0, int((perf_counter() - started) * 1000)),
            outcome="unknown")

    def generate_reply_structured(self, inputs: AgentInput, qualification: QualificationResult,
                                  decision: Decision, *, language: ReplyLanguage | None = None) -> tuple[str, list[UsageInfo]]:
        """Explicit drafting only. The public reply entry point owns eligibility."""
        if inputs.metadata.provider_mode != "real" or decision == Decision.IGNORE:
            raise ProviderError("Real reply requires real mode and a review/respond lead", [])
        plan = plan_reply(inputs, qualification, language)
        messages = build_reply_messages(inputs, qualification, decision, plan=plan)
        records: list[UsageInfo] = []
        manager = (nullcontext(self._client) if self._client is not None else
                   httpx.Client(timeout=self.config.timeout_seconds, follow_redirects=False))
        with manager as client:
            for attempt in (1, 2):
                request_messages = list(messages)
                if attempt == 2:
                    request_messages.insert(1, {"role": "developer", "content":
                        "The previous draft failed local schema, language or grounding checks. "
                        "Regenerate using the exact required acknowledgement, whole Product facts and one safe next-step question. "
                        "Omit uncertain claims. Never include scores, decisions or approval."})
                started = perf_counter()
                try:
                    response = client.post(self.config.responses_url,
                        headers={"Authorization": "Bearer " + self._api_key.get_secret_value()},
                        timeout=self.config.timeout_seconds, follow_redirects=False,
                        json={"model": self.config.model, "store": False,
                              "max_output_tokens": self.config.max_output_tokens,
                              "input": request_messages,
                              "text": {"format": {"type": "json_schema", "name": "suggested_reply",
                                                  "strict": True, "schema": reply_schema()}}})
                except ProviderError:
                    raise ProviderError("OPENAI_BASE_URL must be a trusted Responses endpoint", records) from None
                except (httpx.HTTPError, RuntimeError) as exc:
                    record = self._usage({}, attempt, started, "suggested_reply")
                    record.outcome = "timeout" if isinstance(exc, httpx.TimeoutException) else "provider_error"
                    records.append(record)
                    raise ProviderError("Real reply request timed out" if record.outcome == "timeout"
                                        else "Real reply request failed", records) from None
                try:
                    body = response.json()
                    body = body if isinstance(body, dict) else {}
                except (ValueError, RecursionError):
                    body = {}
                record = self._usage(body, attempt, started, "suggested_reply")
                records.append(record)
                if not response.is_success:
                    record.outcome = "provider_error"
                    raise ProviderError(_http_failure(response.status_code, body), records) from None
                if body.get("status") in ("failed", "cancelled", "incomplete"):
                    record.outcome = "incomplete"
                    raise ProviderError("Real provider did not complete reply generation", records) from None
                try:
                    texts = []
                    for item in body.get("output", []):
                        if item.get("type") == "reasoning":
                            continue
                        if item.get("type") != "message":
                            # No tools are requested or executed. Unexpected tool output is invalid.
                            raise ValueError("unexpected reply output")
                        for part in item.get("content", []):
                            if part.get("type") == "refusal":
                                record.outcome = "refused"
                                raise ProviderError("Real provider refused reply generation", records)
                            if part.get("type") != "output_text":
                                raise ValueError("unexpected reply content")
                            texts.append(part["text"])
                    if body.get("status") != "completed" or len(texts) != 1:
                        raise ValueError("missing or ambiguous structured reply")
                    draft = ReplyDraft.model_validate(json.loads(texts[0]), strict=True)
                    text = render_draft(draft, inputs.product, inputs.message.content, plan=plan)
                    if self._api_key.get_secret_value() in text:
                        raise ValueError("secret in reply output")
                except (ValidationError, ValueError, TypeError, KeyError, AttributeError, RecursionError, ProviderError):
                    if record.outcome == "refused":
                        raise ProviderError("Real provider refused reply generation", records) from None
                    record.outcome = "invalid_output"
                    continue
                record.outcome = "success"
                return text, records
        raise ProviderError("Real reply failed validation after one repair", records) from None

    def qualify_structured(self, product: ProductSnapshot, target: TargetMessage,
                           context: list[TargetMessage]) -> tuple[QualificationResult, list[UsageInfo]]:
        """Selected same-conversation context in; validated qualification out."""
        try:
            messages = build_messages(product, target, context)
        except ValueError:
            raise ProviderError("Provider context must have unique IDs in the target conversation and exclude the target", []) from None
        records: list[UsageInfo] = []
        manager = (nullcontext(self._client) if self._client is not None else
                   httpx.Client(timeout=self.config.timeout_seconds, follow_redirects=False))
        with manager as client:
            for attempt in (1, 2):
                request_messages = list(messages)
                if attempt == 2:
                    # Regenerate from the same sources. Never promote raw model output
                    # or validation error text into trusted repair instructions.
                    request_messages.insert(1, {"role": "developer", "content":
                        "The previous qualification failed local schema or evidence validation. "
                        "Return a corrected qualification in the exact schema using only the supplied sources. "
                        "Use exact source quotes and IDs; never include score or decision."})
                started = perf_counter()
                try:
                    response = client.post(self.config.responses_url,
                        headers={"Authorization": "Bearer " + self._api_key.get_secret_value()},
                        timeout=self.config.timeout_seconds, follow_redirects=False,
                        json={"model": self.config.model, "store": False,
                              "max_output_tokens": self.config.max_output_tokens,
                              "input": request_messages,
                              "text": {"format": {"type": "json_schema", "name": "qualification",
                                                  "strict": True, "schema": output_schema()}}})
                except ProviderError:
                    raise ProviderError("OPENAI_BASE_URL must be a trusted Responses endpoint", records) from None
                except (httpx.HTTPError, RuntimeError) as exc:
                    record = self._usage({}, attempt, started)
                    record.outcome = "timeout" if isinstance(exc, httpx.TimeoutException) else "provider_error"
                    records.append(record)
                    raise ProviderError("Real provider request timed out" if record.outcome == "timeout"
                                        else "Real provider request failed", records) from None
                try:
                    body = response.json()
                    body = body if isinstance(body, dict) else {}
                except (ValueError, RecursionError):
                    body = {}
                record = self._usage(body, attempt, started)
                records.append(record)
                if not response.is_success:
                    record.outcome = "provider_error"
                    raise ProviderError(_http_failure(response.status_code, body), records) from None
                if body.get("status") in ("failed", "cancelled", "incomplete"):
                    record.outcome = "incomplete"
                    raise ProviderError("Real provider did not complete qualification", records) from None
                try:
                    texts = []
                    for item in body.get("output", []):
                        if item.get("type") != "message":
                            continue
                        for part in item.get("content", []):
                            if part.get("type") == "refusal":
                                record.outcome = "refused"
                                raise ProviderError("Real provider refused qualification", records)
                            if part.get("type") == "output_text":
                                texts.append(part["text"])
                    if body.get("status") != "completed" or len(texts) != 1:
                        raise ValueError("missing or ambiguous structured response")
                    # Reject numeric strings, booleans, extras and non-finite numbers.
                    payload = json.loads(texts[0])
                    if not isinstance(payload, dict) or set(QualificationResult.model_fields) - payload.keys():
                        raise ValueError("required structured output fields are missing")
                    result = QualificationResult.model_validate(payload, strict=True)
                    validate_qualification_result(result, target, context, [])
                except (ValidationError, ValueError, TypeError, KeyError, AttributeError, RecursionError, ProviderError):
                    if record.outcome == "refused":
                        raise ProviderError("Real provider refused qualification", records) from None
                    record.outcome = "invalid_output"
                    continue
                record.outcome = "success"
                return result, records
        raise ProviderError("Real provider qualification failed validation after one repair", records) from None

    def qualify(self, product: ProductSnapshot, target: TargetMessage,
                context: list[TargetMessage]) -> tuple[Qualification, list[UsageEvent]]:
        """Legacy adapter; the pipeline's deterministic scorer remains separate."""
        try:
            result, records = self.qualify_structured(product, target, context)
        except ProviderError as exc:
            raise ProviderError(str(exc), _legacy_usage(exc.usage)) from None
        return _legacy_result(result), _legacy_usage(records)

    def analyze(self, inputs: AgentInput) -> AgentOutput:
        """Public boundary: screening + qualification, with scoring left unset."""
        if inputs.metadata.provider_mode != "real":
            raise ProviderError("RealProvider requires explicit provider_mode='real'", [])
        product = ProductSnapshot(**inputs.product.model_dump(exclude={"id"}))
        message = inputs.message
        target = TargetMessage(id=message.id, external_id=message.id,
            content=message.content, author=message.author, timestamp=message.timestamp,
            conversation_id=message.conversation_id, reply_to_external_id=message.reply_to_message_id)
        # ContextMessage has no conversation_id: the caller guarantees isolation.
        context = [TargetMessage(id=m.id, external_id=m.id, content=m.content,
            author=m.author, timestamp=m.timestamp, conversation_id=target.conversation_id)
            for m in inputs.context_messages]
        if len({m.id for m in context}) != len(context) or any(m.id == target.id for m in context):
            raise ProviderError("Provider context must have unique IDs and exclude the target", [])
        screening = screen(product, target, context)
        if not screening.is_candidate:
            return AgentOutput(screening=screening, decision_reason=screening_decision_reason(screening))
        result, usage = self.qualify_structured(product, target, context)
        return AgentOutput(screening=screening, qualification=result, usage=usage, prompt_version=self.prompt_version)
