from app.agents.contracts import ProductSnapshot, TargetMessage, Qualification, Signals, Evidence, UsageEvent
from app.agents.screening import normalize, related
from app.agents.cost import calculate_cost
from app.agents.contracts import AgentInput, AgentOutput, QualificationResult, EvidenceItem, UsageInfo, Decision
from app.agents.providers.base import BaseProvider, ProviderError
from app.agents.screening import screen
from app.agents.scoring import SCORING_VERSION, calculate_score_with_reason, screening_decision_reason
from app.agents.reply_draft import PERSIAN


class MockProvider(BaseProvider):
    """Deterministic demo heuristics, never presented as real AI predictions."""
    provider_mode = "mock"

    def generate_reply_structured(self, inputs: AgentInput, qualification: QualificationResult,
                                  decision: Decision) -> tuple[str, list[UsageInfo]]:
        """Explicitly synthetic development draft, never used by the real path."""
        if inputs.metadata.provider_mode != "mock" or decision == Decision.IGNORE:
            raise ProviderError("Mock reply requires mock mode and a review/respond lead", [])
        text = ("چه چیزی می‌خواهید یاد بگیرید؟" if PERSIAN.search(inputs.message.content)
                else "What would you like to learn or achieve?")
        return text, [UsageInfo(stage="suggested_reply", provider_mode="mock", model="mock",
            estimated_cost=0, cost_status="mock", price_version="mock_v1", outcome="success")]

    def qualify_structured(self, product: ProductSnapshot, target: TargetMessage,
                           context: list[TargetMessage]) -> tuple[QualificationResult, list[UsageInfo]]:
        """Adapt existing Mock qualification and usage without running the scorer."""
        qualified, events = self.qualify(product, target, context)
        result = QualificationResult(intent=qualified.intent, need=qualified.need,
            **qualified.signals.model_dump(),
            evidence=[EvidenceItem(message_id=e.message_id, quote=e.quote, reason=qualified.reason)
                      for e in qualified.evidence], limitations=qualified.limitations)
        return result, self._public_usage(events)

    @staticmethod
    def _public_usage(events: list[UsageEvent]) -> list[UsageInfo]:
        return [UsageInfo(stage=event.stage, attempt_no=event.attempt_no,
            provider_mode=event.provider_mode, model=event.model,
            input_tokens=event.input_tokens, output_tokens=event.output_tokens,
            estimated_cost=event.cost_usd, cost_status=event.cost_status,
            price_version=event.price_version, latency_ms=event.latency_ms,
            outcome=event.outcome) for event in events]

    def analyze(self, inputs: AgentInput) -> AgentOutput:
        if inputs.metadata.provider_mode != "mock":
            raise ValueError("MockProvider requires explicit provider_mode='mock'")
        product = ProductSnapshot(**inputs.product.model_dump(exclude={"id"}))
        message = inputs.message
        target = TargetMessage(id=message.id, external_id=message.id, content=message.content,
            author=message.author, timestamp=message.timestamp, conversation_id=message.conversation_id,
            reply_to_external_id=message.reply_to_message_id)
        # ContextMessage intentionally has no conversation field. The caller is
        # responsible for supplying scoped context; never query persistence here.
        if len({m.id for m in inputs.context_messages}) != len(inputs.context_messages):
            raise ValueError("Context message IDs must be unique")
        if any(m.id == target.id for m in inputs.context_messages):
            raise ValueError("Context must exclude the target message")
        context = [TargetMessage(id=m.id, external_id=m.id, content=m.content, author=m.author,
            timestamp=m.timestamp, conversation_id=target.conversation_id) for m in inputs.context_messages]
        screening = screen(product, target, context)
        if not screening.is_candidate:
            return AgentOutput(screening=screening, decision_reason=screening_decision_reason(screening))
        qualified, events = self.qualify(product, target, context)
        usage = self._public_usage(events)
        scoring, decision_reason = calculate_score_with_reason(qualified.signals,
            valid_purchase_evidence=any(e.message_id == target.id for e in qualified.evidence),
            needs_human_review=qualified.needs_human_review)
        return AgentOutput(screening=screening,
            qualification=QualificationResult(intent=qualified.intent, need=qualified.need,
                purchase_intent=qualified.signals.purchase_intent,
                product_fit=qualified.signals.product_fit, urgency=qualified.signals.urgency,
                confidence=qualified.signals.confidence, need_strength=qualified.signals.need_strength,
                response_opportunity=qualified.signals.response_opportunity,
                evidence=[EvidenceItem(message_id=e.message_id, quote=e.quote, reason=qualified.reason) for e in qualified.evidence],
                limitations=qualified.limitations),
            scoring=scoring, usage=usage, decision_reason=decision_reason, scoring_version=SCORING_VERSION)

    def qualify(self, product: ProductSnapshot, target: TargetMessage, context: list[TargetMessage]) -> tuple[Qualification, list[UsageEvent]]:
        text = normalize(target.content)
        vectors = {
            "request": (.9, .9, .8, .5, .9, .8),
            "price": (.6, .85, .7, .1, .8, .8),
            "technical": (.1, .7, .3, 0, .9, .2),
            "ambiguous": (.3, .5, .4, .1, .4, .4),
            "quotation": (.1, .6, .3, 0, .8, .2),
            "injection": (0, .1, 0, 0, .9, 0),
        }
        if any(w in text for w in ["ignore previous", "امتیاز مرا", "دستورهای قبلی"]):
            kind, reason = "injection", "Untrusted instruction text is treated as message data."
        elif any(w in text for w in ["دوستم", "friend", "نقل قول"]):
            kind, reason = "quotation", "Another person's needs are not attributed to the author."
        elif any(w in text for w in ["گرونه", "گران", "expensive"]) and any(related(m.content, product) for m in context):
            kind, reason = "price", "A price objection is related to the same conversation's product discussion."
        elif any(w in text for w in ["دنبال", "می خوام", "نیاز دارم", "looking for", "want to buy", "register"]) and related(text, product):
            kind, reason = "request", "The author explicitly requests a product matching the supplied profile."
        elif any(w in text for w in ["چطور", "چگونه", "how", "خطا", "error"]):
            kind, reason = "technical", "A technical question alone does not establish purchase intent."
        else:
            kind, reason = "ambiguous", "The message needs human review; intent is uncertain."
        signals = Signals(**dict(zip(Signals.model_fields, vectors[kind])))
        course_product = any(w in normalize(product.name + " " + product.description) for w in ["course", "دوره"])
        result = Qualification(signals=signals, intent=("searching_for_course" if course_product else "searching_for_product") if kind == "request" else kind,
            need=(f"Seeking {product.name}" if kind == "request" else "Uncertain or contextual need"),
            reason=reason, evidence=[Evidence(message_id=target.id, quote=target.content)],
            limitations=["Synthetic Mock output; not an AI prediction", "Budget is unknown", "Urgency is not inferred beyond the demo fixture"],
            needs_human_review=kind == "ambiguous")
        cost = calculate_cost("mock", None, None, None)
        return result, [UsageEvent(cost_usd=str(cost.cost_usd), cost_status=cost.cost_status, price_version=cost.price_version)]
