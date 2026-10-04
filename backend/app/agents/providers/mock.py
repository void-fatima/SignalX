from app.agents.contracts import ProductSnapshot, TargetMessage, Qualification, Signals, Evidence, UsageEvent
from app.agents.screening import normalize, related
from app.agents.cost import calculate_cost


class MockProvider:
    """Deterministic demo heuristics, never presented as real AI predictions."""
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
