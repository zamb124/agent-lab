"""
API для получения участников команды компании.

Доступен во всех сервисах через core/app/factory.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from core.app_state import require_platform_app_state
from core.context import get_context
from core.identity.flow_employee import (
    flow_employee_curator_user_ids,
    is_flow_employee,
    require_flow_employee_flow_id,
)
from core.pagination import ListResponse
from core.utils.auth_session_rebind import attach_session_auth_cookie
from core.utils.tokens import TokenService, get_token_service

router = APIRouter(tags=["team"])

_COMPANY_ADMIN_ROLES: frozenset[str] = frozenset({"admin", "owner"})


class TeamMemberResponse(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    joined_at: datetime | None = None
    avatar_url: str | None = None
    is_flow_employee: bool = False
    flow_id: str | None = None
    curator_user_ids: list[str] = Field(default_factory=list)


@router.get("/members", response_model=ListResponse[TeamMemberResponse])
async def get_team_members(request: Request) -> ListResponse[TeamMemberResponse]:
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    company = ctx.active_company
    app_state = require_platform_app_state(request)
    company_repo = app_state.container.company_repository
    user_repo = app_state.container.user_repository
    stored_company = await company_repo.get(company.company_id)
    if stored_company is None:
        raise HTTPException(status_code=404, detail=f"Company {company.company_id} not found")

    members: list[TeamMemberResponse] = []
    for user_id, roles in stored_company.members.items():
        member_user = await user_repo.get(user_id)
        if not member_user:
            continue
        member_email = member_user.emails[0] if member_user.emails else None
        member_is_employee = is_flow_employee(member_user)
        members.append(TeamMemberResponse(
            user_id=user_id,
            name=member_user.name,
            email=member_email,
            roles=roles,
            joined_at=member_user.created_at,
            avatar_url=member_user.avatar_url,
            is_flow_employee=member_is_employee,
            flow_id=require_flow_employee_flow_id(member_user) if member_is_employee else None,
            curator_user_ids=flow_employee_curator_user_ids(member_user) if member_is_employee else [],
        ))

    return ListResponse[TeamMemberResponse](items=members)


class UserSearchResult(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    avatar_url: str | None = None


@router.get("/search", response_model=ListResponse[UserSearchResult])
async def search_users(
    request: Request,
    q: Annotated[str, Query(min_length=2, description="Email или имя для поиска")],
) -> ListResponse[UserSearchResult]:
    """Поиск пользователей по email или имени (по всем компаниям)."""
    ctx = get_context()
    if ctx is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    app_state = require_platform_app_state(request)
    user_repo = app_state.container.user_repository
    users = await user_repo.search_by_query(q, limit=20)

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
async def act_as_employee(request: Request, user_id: str) -> Response:
    """Куратор/админ действует от имени flow-сотрудника (короткоживущий SESSION JWT)."""
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    caller_id = ctx.user.user_id

    app_state = require_platform_app_state(request)
    user_repo = app_state.container.user_repository
    company_repo = app_state.container.company_repository

    target = await user_repo.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    if not is_flow_employee(target):
        raise HTTPException(status_code=403, detail="act-as разрешён только для flow-сотрудников")

    company_id = ctx.active_company.company_id
    if company_id not in target.companies:
        raise HTTPException(status_code=403, detail="Сотрудник не состоит в этой компании")

    stored_company = await company_repo.get(company_id)
    if stored_company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    caller_roles = stored_company.members.get(caller_id, [])
    curators = flow_employee_curator_user_ids(target)
    is_admin = bool(_COMPANY_ADMIN_ROLES.intersection(caller_roles))
    if caller_id not in curators and not is_admin:
        raise HTTPException(status_code=403, detail="Только куратор или админ компании может войти как сотрудник")

    roles = target.companies[company_id]
    if not roles:
        raise HTTPException(status_code=409, detail="У сотрудника нет ролей в компании")

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
        raise HTTPException(status_code=409, detail="Сессия не в режиме act-as")

    app_state = require_platform_app_state(request)
    user_repo = app_state.container.user_repository
    company_repo = app_state.container.company_repository

    curator = await user_repo.get(impersonated_by)
    if curator is None:
        raise HTTPException(status_code=404, detail=f"User {impersonated_by} not found")

    company_id = curator.active_company_id or ctx.active_company.company_id
    stored_company = await company_repo.get(company_id)
    if stored_company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    roles = stored_company.members.get(curator.user_id, [])
    if not roles:
        raise HTTPException(status_code=409, detail="У куратора нет ролей в компании")

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
