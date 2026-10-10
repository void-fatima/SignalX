"""Character/output budgets are deterministic, not fabricated token estimates."""
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.agents.contracts import Decision
from app.agents.prompts.reply import build_reply_messages, REPLY_MAX_OUTPUT_TOKENS
from app.agents.providers.base import ProviderError
from app.agents.reply import generate_suggested_reply
from test_intent_aware_replies import planned_draft
from test_reply_plan import inputs as make_input
from test_suggested_reply import real_provider, qualified, analysis_for, envelope


def context(id, text):
    return dict(id=id, content=text, author="Buyer", timestamp=datetime(2026, 10, 10, tzinfo=timezone.utc))


def test_duplicate_context_removed_without_mutating_snapshots():
    item = make_input("Pricing please", [context("a", "We need invoices."), context("b", "We need invoices.")])
    q = qualified(item)
    before = deepcopy(item.model_dump())
    data = json.loads(build_reply_messages(item, q, Decision.RESPOND)[-1]["content"])
    assert len(data["context"]) == 1 and data["context_omitted_ids"] == ["b"]
    assert item.model_dump() == before and data["product"] == item.product.model_dump(mode="json")
    assert "evidence" not in data["qualification"] and "product_fit" not in data["qualification"]


def test_over_budget_context_is_omitted_whole_and_explicitly_marked():
    item = make_input("Pricing please", [context("a", "first " * 500), context("b", "not available " * 200)])
    data = json.loads(build_reply_messages(item, qualified(item), Decision.REVIEW)[-1]["content"])
    assert data["context"][0]["content"] == item.context_messages[0].content
    assert data["context_omitted_ids"] == ["b"] and data["human_review_required"]


def test_oversized_product_fails_before_http_not_silently_truncated(real_provider):
    item = make_input("Pricing please")
    item.product.description = "a" * 21000
    _, requests, _ = real_provider([])
    with pytest.raises(ProviderError, match="budget"):
        generate_suggested_reply(item, analysis_for(item))
    assert requests == []


def test_reply_request_budget_does_not_change_qualification_config(real_provider):
    item = make_input("Pricing please")
    q = qualified(item)
    provider, requests, _ = real_provider([envelope(planned_draft(item, q))])
    prior_limit = provider.config.max_output_tokens
    result = generate_suggested_reply(item, analysis_for(item, q))
    assert json.loads(requests[0].content)["max_output_tokens"] == min(prior_limit, REPLY_MAX_OUTPUT_TOKENS)
    assert provider.config.max_output_tokens == prior_limit
    assert result.usage[-1].input_tokens == 100 and result.usage[-1].output_tokens == 20
    assert result.usage[-1].estimated_cost is None and result.usage[-1].cost_status == "unknown"