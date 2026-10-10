from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from app.auth.dependencies import get_current_user, verify_origin
from app.auth.contracts import CurrentUser
from app.schemas.api import ErrorOut
from app.db.session import get_session
from sqlalchemy.orm import Session
from app.discovery.models import DiscoverySearch, DiscoveryProspect
from app.discovery.schemas import SearchInput, SearchOut, SaveInput, ProspectOut, SourcesOut
from app.discovery.providers import source_status
from app.discovery.service import owned, perform_search, search_out, save_prospects

router=APIRouter(prefix="/discovery",tags=["Discovery"],responses={status:{"model":ErrorOut} for status in (401,403,429,503,504)})
DB=Annotated[Session,Depends(get_session)]
Current=Annotated[CurrentUser,Depends(get_current_user)]

@router.get("/sources",response_model=SourcesOut)
def sources(current:Current):
    return {"items":[source_status(source) for source in ("brave","greenhouse","lever","places")]}

@router.post("/searches",response_model=SearchOut,dependencies=[Depends(verify_origin)])
def search(payload:SearchInput,session:DB,current:Current,key:Annotated[str,Header(alias="Idempotency-Key")]):
    return perform_search(session,str(current.id),payload,key)

@router.get("/searches",response_model=list[SearchOut])
def history(session:DB,current:Current,limit:Annotated[int,Query(ge=1,le=50)]=20,offset:Annotated[int,Query(ge=0)]=0):
    rows=session.scalars(select(DiscoverySearch).where(DiscoverySearch.user_id==str(current.id)).order_by(DiscoverySearch.created_at.desc(),DiscoverySearch.id).limit(limit).offset(offset)).all()
    return [search_out(row) for row in rows]

@router.get("/searches/{id}",response_model=SearchOut)
def detail(id:UUID,session:DB,current:Current):
    return search_out(owned(session,DiscoverySearch,id,str(current.id)))

@router.post("/prospects",response_model=list[ProspectOut],dependencies=[Depends(verify_origin)])
def save(payload:SaveInput,session:DB,current:Current):
    return save_prospects(session,str(current.id),payload)

@router.get("/prospects",response_model=list[ProspectOut])
def prospects(session:DB,current:Current,limit:Annotated[int,Query(ge=1,le=50)]=20,offset:Annotated[int,Query(ge=0)]=0):
    return session.scalars(select(DiscoveryProspect).where(DiscoveryProspect.user_id==str(current.id)).order_by(DiscoveryProspect.created_at.desc(),DiscoveryProspect.id).limit(limit).offset(offset)).all()

@router.post("/prospects/{id}/qualify",response_model=ProspectOut,dependencies=[Depends(verify_origin)])
def qualify(id:UUID,session:DB,current:Current,key:Annotated[str,Header(alias="Idempotency-Key")]):
    from app.discovery.qualification import qualify_prospect
    return qualify_prospect(session,str(current.id),str(id),key)
