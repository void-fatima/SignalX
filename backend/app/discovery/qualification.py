"""Explicit one-prospect assessment; message lead decisions never become prospect intent."""
import hashlib
import os
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.agents.contracts import AgentInput, AgentMetadata, MessageInput, ProductInput, UsageInfo
from app.agents.orchestrator import analyze_agent
from app.agents.providers.base import ProviderError
from app.agents.providers.config import RealProviderConfig
from app.core.config import settings
from app.core.errors import AppError
from app.discovery.models import DiscoveryProspect, DiscoverySearch
from app.discovery.service import owned, key_value, budget
from app.models import User, Product, utcnow


def qualify_prospect(session: Session, user_id: str, prospect_id: str, key: str) -> DiscoveryProspect:
    key = key_value(key)
    session.scalar(select(User).where(User.id == user_id).with_for_update())
    row = owned(session, DiscoveryProspect, prospect_id, user_id, lock=True)
    owned(session, Product, row.product_id, user_id)
    search = owned(session, DiscoverySearch, row.search_id, user_id)
    if row.qualification_key:
        if row.qualification_key != key:
            raise AppError("evaluation_already_requested", "Evaluation was already requested; reuse its original key", 409)
        return row  # Pending and failed operations are never automatically retried.
    if row.source == "places" or not row.excerpt.strip():
        raise AppError("insufficient_source", "This source has no retained excerpt suitable for AI evaluation", 422)
    try:
        config = RealProviderConfig.from_env()
        if (settings().provider_mode != "real" or config.base_url != "https://api.avalai.ir/v1"
                or os.getenv("LLM_PROVIDER", "avalai") != "avalai"
                or not os.getenv("OPENAI_API_KEY", "").strip() or config.max_output_tokens > 2000):
            raise ValueError("configuration unavailable")
        inputs = AgentInput(product=ProductInput.model_validate(search.product_snapshot),
            message=MessageInput(id=row.id, content=row.title + "\n" + row.excerpt,
                author="Public source; authorship and buying intent are not verified",
                timestamp=row.created_at, conversation_id="discovery:" + row.id),
            metadata=AgentMetadata(run_id="discovery:" + row.id, provider_mode="real"))
        if len(inputs.model_dump_json()) > 20000:
            raise ValueError("input budget exceeded")
    except (ProviderError, ValueError):
        raise AppError("evaluation_unavailable", "Real AvalAI evaluation configuration or input budget is unavailable", 503) from None
    now = utcnow()
    scope = "q_" + hashlib.sha256(user_id.encode()).hexdigest()[:16]
    budget(session, scope, now, hourly_limit=3, cooldown=60)
    budget(session, "qualification", now, hourly_limit=10, cooldown=2)
    row.qualification_key = key
    row.qualification_status = "pending"
    session.commit()  # Durable reservation precedes the only explicit Agent operation.
    try:
        output = analyze_agent(inputs)
    except ProviderError as exc:
        row.qualification_usage = [UsageInfo.model_validate(u.model_dump()).model_dump(mode="json") for u in exc.usage]
        row.qualification_status = "failed"
        row.qualification_error = "AvalAI evaluation failed; no automatic retry or provider fallback was made."
        session.commit()
        return row
    except (ValueError, TypeError):
        row.qualification_status = "failed"
        row.qualification_error = "Evaluation input or grounded output could not be validated."
        session.commit()
        return row
    # Commit real attempt metadata independently of downstream projection.
    row.qualification_usage = [u.model_dump(mode="json") for u in output.usage]
    session.commit()
    try:
        row.agent_output = output.model_dump(mode="json")
        row.signal = "not_evaluated"
        row.explanation = "Source evidence is insufficient to establish product relevance. Buying intent remains unverified."
        q = output.qualification
        if q and q.evidence and q.product_fit >= .5 and q.confidence >= .6:
            row.signal = "possible_need" if q.need_strength >= .5 else "relevant_company"
            row.explanation = ("Grounded source excerpt suggests possible need." if row.signal == "possible_need" else "Grounded source excerpt suggests product relevance.")
            row.explanation += " Public-source authorship and buying intent are unverified; hiring is not a purchasing request."
        row.qualification_status = "completed"
        session.commit()
    except Exception:
        session.rollback()
        row = owned(session, DiscoveryProspect, prospect_id, user_id)
        row.qualification_status = "failed"
        row.qualification_error = "Evaluation projection could not be persisted; provider usage was retained."
        session.commit()
    return row
