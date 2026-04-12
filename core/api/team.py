"""
API для получения участников команды компании.

Доступен во всех сервисах через core/app/factory.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.context import get_context

router = APIRouter(tags=["team"])


class TeamMemberResponse(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    joined_at: datetime | None = None
    avatar_url: str | None = None


@router.get("/members", response_model=list[TeamMemberResponse])
async def get_team_members(request: Request) -> list[TeamMemberResponse]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")

    company = ctx.active_company
    company_repo = request.app.state.container.company_repository
    user_repo = request.app.state.container.user_repository
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
            roles=roles if isinstance(roles, list) else [roles],
            joined_at=member_user.created_at,
            avatar_url=member_user.avatar_url,
        ))

    return members


class UserSearchResult(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    avatar_url: str | None = None


@router.get("/search", response_model=list[UserSearchResult])
async def search_users(
    request: Request,
    q: str = Query(..., min_length=2, description="Email или имя для поиска"),
) -> list[UserSearchResult]:
    """Поиск пользователей по email или имени (по всем компаниям)."""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_repo = request.app.state.container.user_repository
    users = await user_repo.search_by_query(q, limit=20)

    return [
        UserSearchResult(
            user_id=u.user_id,
            name=u.name,
            email=u.emails[0] if u.emails else None,
            avatar_url=u.avatar_url,
        )
        for u in users
    ]
