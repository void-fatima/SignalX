"""User-scoped explicit searches. Quotas are reserved before external I/O."""
from datetime import timedelta
import hashlib
import json
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.models import User, Product, utcnow
from app.core.errors import AppError
from app.discovery.models import DiscoverySearch, DiscoveryProspect, DiscoveryBudget
from app.discovery.schemas import SearchOut, DiscoveryResult
from app.discovery.providers import DiscoveryError, get_discovery_provider, public_url, source_status

CACHE_SECONDS = 900
USER_SEARCHES_PER_HOUR = 5
GLOBAL_SEARCHES_PER_SOURCE_HOUR = 100

def owned(session, model, id, user_id, *, lock=False):
    statement=select(model).where(model.id==str(id),model.user_id==str(user_id))
    row=session.scalar(statement.with_for_update() if lock else statement)
    if row is None: raise AppError("not_found","Record does not exist",404)
    return row

def key_value(key):
    if not key or not key.strip() or len(key)>200 or any(ord(c)<33 for c in key):
        raise AppError("invalid_idempotency_key","A bounded nonempty Idempotency-Key is required",422)
    return key

def budget(session, scope, now, *, hourly_limit=100, cooldown=2):
    row=session.scalar(select(DiscoveryBudget).where(DiscoveryBudget.source==scope).with_for_update())
    if row is None:
        try:
            with session.begin_nested():
                row=DiscoveryBudget(source=scope,window_started_at=now,request_count=0)
                session.add(row); session.flush()
        except IntegrityError:
            row=session.scalar(select(DiscoveryBudget).where(DiscoveryBudget.source==scope).with_for_update())
        if row is None: raise AppError("discovery_busy","Discovery budget could not be reserved",409)
    if row.last_request_at and row.last_request_at > now-timedelta(seconds=cooldown):
        raise AppError("discovery_rate_limit","Wait before another explicit discovery request",429)
    if row.window_started_at <= now-timedelta(hours=1):
        row.window_started_at=now; row.request_count=0
    if row.request_count >= hourly_limit: raise AppError("discovery_quota","Discovery request budget exhausted for this hour",429)
    row.request_count+=1; row.last_request_at=now

def search_out(row, *, cached=False):
    return SearchOut(id=row.id,product_id=row.product_id,source=row.source,status=row.status,
        results=[DiscoveryResult.model_validate(r) for r in row.results],cached=cached,
        request_count=0 if cached else row.request_count,error_code=row.error_code,error=row.error,created_at=row.created_at)

def perform_search(session, user_id, inputs, key):
    key=key_value(key)
    product=owned(session,Product,inputs.product_id,user_id)
    # No duplicate Workspace/Business. Existing User row serializes reservations.
    session.scalar(select(User).where(User.id==str(user_id)).with_for_update())
    snapshot={field:getattr(product,field) for field in ("id","name","description","target_customer")}
    query=inputs.model_dump(mode="json")
    fingerprint=hashlib.sha256(json.dumps([query,snapshot],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    previous=session.scalar(select(DiscoverySearch).where(DiscoverySearch.user_id==str(user_id),DiscoverySearch.idempotency_key==key))
    if previous:
        if previous.fingerprint != fingerprint: raise AppError("idempotency_conflict","Search key was already used for different inputs",409)
        return search_out(previous,cached=True)
    configured=source_status(inputs.source)
    if not configured.configured: raise AppError("configuration_required",configured.message,503)
    now=utcnow()
    if inputs.source != "places":
        cached=session.scalar(select(DiscoverySearch).where(DiscoverySearch.user_id==str(user_id),DiscoverySearch.fingerprint==fingerprint,
            DiscoverySearch.status=="completed",DiscoverySearch.created_at>now-timedelta(seconds=CACHE_SECONDS)).order_by(DiscoverySearch.created_at.desc()).limit(1))
        if cached: return search_out(cached,cached=True)
    recent=select(DiscoverySearch).where(DiscoverySearch.user_id==str(user_id),DiscoverySearch.created_at>now-timedelta(hours=1))
    if session.scalar(select(func.count()).select_from(recent.subquery())) >= USER_SEARCHES_PER_HOUR:
        raise AppError("discovery_quota","Your hourly discovery search budget is exhausted",429)
    latest=session.scalar(recent.order_by(DiscoverySearch.created_at.desc()).limit(1))
    if latest and latest.created_at>now-timedelta(seconds=60): raise AppError("discovery_rate_limit","Wait one minute before starting a different search",429)
    budget(session,inputs.source,now,hourly_limit=GLOBAL_SEARCHES_PER_SOURCE_HOUR)
    row=DiscoverySearch(user_id=str(user_id),product_id=product.id,source=inputs.source,idempotency_key=key,
        fingerprint=fingerprint,query=query,product_snapshot=snapshot,status="pending",results=[],request_count=0)
    session.add(row); session.commit()  # Release locks; keep the durable reservation on failures.
    try:
        results=get_discovery_provider(inputs.source).search(inputs)
        # Trust neither injected adapters nor upstream data at the persistence boundary.
        results=[DiscoveryResult.model_validate(item.model_dump(),strict=True) for item in results]
        if len(results)>inputs.limit or len({r.source_id for r in results}) != len(results):
            raise DiscoveryError("source_invalid_output","Source result budget or IDs are invalid",502,1)
        for result in results:
            if result.source != inputs.source or public_url(result.url) != result.url:
                raise DiscoveryError("source_invalid_output","Source attribution or URL is invalid",502,1)
        row.results=[item.model_dump() for item in results]; row.status="completed"; row.request_count=1
    except DiscoveryError as exc:
        row.status="failed"; row.request_count=exc.request_count; row.error_code=exc.code; row.error=str(exc)
    except (ValueError,TypeError,AttributeError):
        row.status="failed"; row.request_count=1; row.error_code="source_invalid_output"; row.error="Discovery source returned invalid normalized results."
    session.commit()
    return search_out(row)

def save_prospects(session,user_id,payload):
    search=owned(session,DiscoverySearch,payload.search_id,user_id)
    owned(session,Product,search.product_id,user_id)
    if search.status != "completed": raise AppError("search_not_completed","Only completed results can be saved",409)
    items={r["source_id"]:DiscoveryResult.model_validate(r) for r in search.results}
    if any(id not in items for id in payload.source_ids): raise AppError("invalid_selection","Selected result does not belong to this search",422)
    session.scalar(select(User).where(User.id==str(user_id)).with_for_update())
    saved=[]
    for id in payload.source_ids:
        result=items[id]
        existing=session.scalar(select(DiscoveryProspect).where(DiscoveryProspect.user_id==str(user_id),DiscoveryProspect.product_id==search.product_id,DiscoveryProspect.source==search.source,DiscoveryProspect.source_id==id))
        if existing: saved.append(existing); continue
        row=DiscoveryProspect(user_id=str(user_id),product_id=search.product_id,search_id=search.id,
            **result.model_dump(),qualification_usage=[],qualification_status="not_requested")
        session.add(row); saved.append(row)
    session.commit()
    return saved
