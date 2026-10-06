"""OpenAI Responses qualification adapter. No scoring, persistence or fallback."""
import json
import os
from contextlib import nullcontext
from time import perf_counter

import httpx
from pydantic import SecretStr, ValidationError

from app.agents.contracts import (
    AgentInput, AgentOutput, Evidence, ProductSnapshot, Qualification,
    QualificationResult, Signals, TargetMessage, UsageEvent, UsageInfo,
)
from app.agents.cost import calculate_cost
from app.agents.prompts.qualification import PROMPT_VERSION, build_messages, output_schema
from app.agents.providers.base import BaseProvider, ProviderError
from app.agents.providers.config import RealProviderConfig
from app.agents.qualification import validate_qualification_result
from app.agents.screening import screen


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

    def _usage(self, body: dict, attempt: int, started: float) -> UsageInfo:
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
        return UsageInfo(stage="qualification" if attempt == 1 else "qualification_repair",
            attempt_no=attempt, provider_mode="real", model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            estimated_cost=cost.cost_usd, cost_status=cost.cost_status,
            price_version=cost.price_version, latency_ms=max(0, int((perf_counter() - started) * 1000)),
            outcome="unknown")

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
                    response = client.post("https://api.openai.com/v1/responses",
                        headers={"Authorization": "Bearer " + self._api_key.get_secret_value()},
                        timeout=self.config.timeout_seconds, follow_redirects=False,
                        json={"model": self.config.model, "store": False,
                              "max_output_tokens": self.config.max_output_tokens,
                              "input": request_messages,
                              "text": {"format": {"type": "json_schema", "name": "qualification",
                                                  "strict": True, "schema": output_schema()}}})
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
                    raise ProviderError("Real provider returned an unsuccessful HTTP response", records) from None
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
            return AgentOutput(screening=screening)
        result, usage = self.qualify_structured(product, target, context)
        return AgentOutput(screening=screening, qualification=result, usage=usage)
