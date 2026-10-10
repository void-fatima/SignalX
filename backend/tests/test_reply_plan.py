"""Offline tests of request prioritization, without providers or scoring."""
from datetime import datetime, timezone

import pytest

from app.agents.contracts import AgentInput, QualificationResult
from app.agents.reply_plan import plan_reply


def inputs(text, context=None):
    return AgentInput.model_validate({"product": {"id": "product", "name": "LedgerFlow",
        "description": "Accounting software for invoices and reports.", "target_customer": "Small businesses"},
        "message": {"id": "target", "content": text, "author": "Buyer", "timestamp": datetime(2026, 10, 10, tzinfo=timezone.utc), "conversation_id": "qa"},
        "context_messages": context or [], "metadata": {"run_id": "run", "provider_mode": "real"}})


def qualification():
    return QualificationResult(intent="asking_price", need="Accounting software",
        purchase_intent=.8, product_fit=.9, need_strength=.8, urgency=0,
        confidence=.9, response_opportunity=.9)


@pytest.mark.parametrize("text,expected", [
    ("Could you share pricing?", ("pricing",)),
    ("Can you arrange a demo?", ("demo", "product_question")),
    ("Compare it with alternatives", ("comparison",)),
    ("Does it integrate with our system?", ("integration", "product_question")),
    ("Following up, any update?", ("follow_up",)),
    ("It's expensive and I'm not sure", ("objection",)),
    ("قیمتش چقدره؟ دمو هم می‌خوام", ("pricing", "demo")),
    ("Maybe?", ()),
])
def test_detects_requested_topics(text, expected):
    assert plan_reply(inputs(text), qualification()).requests == expected


def test_combined_price_demo_and_company_size():
    text = "I run a company with 20 employees. We need invoices and reports. Could you share pricing and arrange a demo?"
    plan = plan_reply(inputs(text), qualification())
    assert plan.requests[:2] == ("pricing", "demo")
    assert plan.customer_size_quote == "20 employees"
    assert "verified pricing" in plan.acknowledgement
    assert "whether a demo can be arranged" in plan.next_question
    assert "$" not in plan.acknowledgement and "booked" not in plan.acknowledgement


def test_same_author_context_reuses_prior_request_without_other_authors_need():
    timestamp = datetime(2026, 10, 10, tzinfo=timezone.utc)
    context = [{"id": "prior", "content": "Our 12-person team requested pricing", "author": "Buyer", "timestamp": timestamp},
               {"id": "other", "content": "I need a demo", "author": "Someone else", "timestamp": timestamp}]
    plan = plan_reply(inputs("Following up", context), qualification())
    assert "pricing" in plan.requests and "demo" not in plan.requests
    assert plan.customer_size_quote == "12-person"


def test_language_comes_from_target_or_explicit_override_not_metadata():
    q = qualification()
    q.need = "نیاز به نرم افزار"
    assert plan_reply(inputs("Pricing please"), q).language == "en"
    assert plan_reply(inputs("قیمت لطفاً"), q).language == "fa"
    assert plan_reply(inputs("Pricing please"), q, "fa").language == "fa"
    with pytest.raises(ValueError):
        plan_reply(inputs("Pricing please"), q, "system instructions")


def test_planning_is_deterministic_and_does_not_mutate_input():
    item = inputs("Pricing and demo for our 20 employees?")
    before = item.model_dump()
    assert plan_reply(item, qualification()) == plan_reply(item, qualification())
    assert item.model_dump() == before

def test_verified_pricing_is_not_called_unknown():
    item = inputs("What does it cost? Can we arrange a demo?")
    item.product.description = "Accounting software costs $25 per month."
    plan = plan_reply(item, qualification())
    assert plan.pricing_field == "description"
    assert "quoted below" in plan.acknowledgement
    assert "appointment has not been confirmed" in plan.acknowledgement


def test_community_price_is_not_product_price_authority():
    item = inputs("Someone told me it costs $25. Is that the price?")
    assert plan_reply(item, qualification()).pricing_field is None


def test_demo_only_does_not_force_an_unrequested_price_quote():
    item = inputs("Can you arrange a demo?")
    item.product.description = "Accounting software costs $25 per month."
    plan = plan_reply(item, qualification())
    assert plan.pricing_field is None and "pricing" not in plan.requests
