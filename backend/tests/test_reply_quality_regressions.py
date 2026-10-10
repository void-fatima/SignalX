"""Offline multilingual natural reply regressions."""
import json
import pytest
from app.agents.reply import generate_suggested_reply
from app.agents.reply_plan import plan_reply
from test_reply_plan import inputs as make_input
from test_suggested_reply import real_provider,analysis_for,qualified,envelope
from test_intent_aware_replies import planned_draft

@pytest.mark.parametrize("message,language",[("Can we discuss a demo?","en"),("دمو می‌خواهم؛ چه کار کنم؟","fa"),("Could we discuss a demo برای تیم ما؟","fa")])
def test_natural_demo_draft_preserves_language_usage_and_token_budget(message,language,real_provider):
    item=make_input(message);q=qualified(item);original=analysis_for(item,q)
    plan=plan_reply(item,q);assert plan.language==language
    _,requests,_=real_provider([envelope(planned_draft(item,q))])
    result=generate_suggested_reply(item,original)
    assert len(requests)==1 and result.scoring==original.scoring
    assert result.usage[:-1]==original.usage and result.usage[-1].outcome=="success"
    assert result.suggested_reply==plan.acknowledgement+" "+plan.next_question
    assert "appointment" not in result.suggested_reply and "confirmed" not in result.suggested_reply
    assert "تأیید نشده" not in result.suggested_reply
    assert json.loads(requests[0].content)["max_output_tokens"]==1200
