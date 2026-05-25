"""
API для получения участников команды компании.

Доступен во всех сервисах через core/app/factory.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.app_state import require_platform_app_state
from core.context import get_context
from core.pagination import ListResponse

router = APIRouter(tags=["team"])


class TeamMemberResponse(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    joined_at: datetime | None = None
    avatar_url: str | None = None


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
        members.append(TeamMemberResponse(
            user_id=user_id,
            name=member_user.name,
            email=member_email,
            roles=roles,
            joined_at=member_user.created_at,
            avatar_url=member_user.avatar_url,
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
