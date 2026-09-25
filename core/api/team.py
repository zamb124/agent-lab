"""
API для получения участников команды компании.

Доступен во всех сервисах через core/app/factory.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse, Response

from core.context import get_context, require_context
from core.di.platform import Di
from core.identity.flow_employee import flow_employee_curator_user_ids, is_flow_employee
from core.identity.team_operations import TeamMemberResponse, op_team_members_list
from core.models.identity_models import Company, User
from core.pagination import ListResponse
from core.utils.auth_session_rebind import attach_session_auth_cookie
from core.utils.tokens import TokenService, get_token_service
from core.websocket import EmptyPayload

router = APIRouter(tags=["team"])


@router.get("/members", response_model=ListResponse[TeamMemberResponse])
async def get_team_members(di: Di) -> ListResponse[TeamMemberResponse]:
    return await op_team_members_list(EmptyPayload(), user=require_context().user, di=di)


class UserSearchResult(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    avatar_url: str | None = None


@router.get("/search", response_model=ListResponse[UserSearchResult])
async def search_users(
    q: Annotated[str, Query(min_length=2, description="Email или имя для поиска")],
) -> ListResponse[UserSearchResult]:
    """Поиск пользователей по email или имени (по всем компаниям)."""
    ctx = get_context()
    if ctx is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    users = await User.search_by_query(q, limit=20)

    return ListResponse[UserSearchResult](items=[
        UserSearchResult(
            user_id=u.user_id,
            name=u.name,
            email=u.emails[0] if u.emails else None,
            avatar_url=u.avatar_url,
        )
        for u in users
    ])


class ActAsResponse(BaseModel):
    user_id: str
    company_id: str
    impersonated_by: str | None = None


_ACT_AS_TTL_SECONDS = 3600


@router.post("/employees/{user_id}/act-as", response_model=ActAsResponse)
async def act_as_employee(request: Request, user_id: str, di: Di) -> Response:
    """Куратор/админ действует от имени flow-сотрудника (короткоживущий SESSION JWT)."""
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    caller_id = ctx.user.user_id

    target = await User.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    if not is_flow_employee(target):
        raise HTTPException(status_code=403, detail='act-as is allowed only for flow employees')

    company_id = ctx.active_company.company_id
    if company_id not in target.companies:
        raise HTTPException(status_code=403, detail='Employee is not a member of this company')

    stored_company = await Company.get(company_id)
    if stored_company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    curators = flow_employee_curator_user_ids(target)
    is_admin = await di.authz_service.check_company_admin(
        company_id=company_id,
        user_id=caller_id,
    )
    if caller_id not in curators and not is_admin:
        raise HTTPException(status_code=403, detail='Only a curator or company admin can sign in as an employee')

    roles = target.companies[company_id]
    if not roles:
        raise HTTPException(status_code=409, detail='Employee has no roles in the company')

    token_service = get_token_service()
    token = token_service.create_token(
        user_id=target.user_id,
        company_id=company_id,
        roles=roles,
        expires_in=_ACT_AS_TTL_SECONDS,
        metadata={"impersonated_by": caller_id},
        email=target.email,
    )
    response = JSONResponse(
        content=ActAsResponse(
            user_id=target.user_id,
            company_id=company_id,
            impersonated_by=caller_id,
        ).model_dump(mode="json")
    )
    attach_session_auth_cookie(response, request, token)
    return response


@router.post("/employees/act-as/stop", response_model=ActAsResponse)
async def stop_act_as(request: Request) -> Response:
    """Возврат куратора в собственную сессию из режима act-as."""
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    impersonated_by = ctx.metadata.get("impersonated_by")
    if not isinstance(impersonated_by, str) or not impersonated_by:
        raise HTTPException(status_code=409, detail='Session is not in act-as mode')

    curator = await User.get(impersonated_by)
    if curator is None:
        raise HTTPException(status_code=404, detail=f"User {impersonated_by} not found")

    company_id = curator.active_company_id or ctx.active_company.company_id
    stored_company = await Company.get(company_id)
    if stored_company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    roles = stored_company.members.get(curator.user_id, [])
    if not roles:
        raise HTTPException(status_code=409, detail='Curator has no roles in the company')

    token_service = get_token_service()
    token = token_service.create_token(
        user_id=curator.user_id,
        company_id=company_id,
        roles=roles,
        expires_in=TokenService.SESSION_EXPIRES,
        email=curator.email,
    )
    response = JSONResponse(
        content=ActAsResponse(user_id=curator.user_id, company_id=company_id).model_dump(mode="json")
    )
    attach_session_auth_cookie(response, request, token)
    return response
