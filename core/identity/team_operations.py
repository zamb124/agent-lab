"""Команда списка участников компании — общая для консоли (`frontend/team/list_requested`),
Documents (`office/company_members/list_requested`) и REST `GET /{svc}/api/team/members`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.container.base import BaseContainer
from core.errors.boundary import PlatformNotFoundError
from core.identity.flow_employee import (
    flow_employee_curator_user_ids,
    is_flow_employee,
    require_flow_employee_flow_id,
)
from core.models.identity_models import User
from core.pagination import ListResponse
from core.request_scope import require_company_viewer
from core.websocket import EmptyPayload


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


async def op_team_members_list(
    payload: EmptyPayload, *, user: User, container: BaseContainer
) -> ListResponse[TeamMemberResponse]:
    """Roster активной компании с признаками flow-сотрудников; Check `company` viewer."""
    _ = payload, user
    scope = await require_company_viewer(container.authz_service)
    company = await container.company_repository.get(scope.company_id)
    if company is None:
        raise PlatformNotFoundError(f"Company {scope.company_id} not found", error_code="not_found")
    users_by_id = await container.user_repository.get_many(list(company.members.keys()))
    members: list[TeamMemberResponse] = []
    for member_user_id, roles in company.members.items():
        member_user = users_by_id.get(member_user_id)
        if member_user is None:
            continue
        member_is_employee = is_flow_employee(member_user)
        members.append(
            TeamMemberResponse(
                user_id=member_user_id,
                name=member_user.name,
                email=member_user.emails[0] if member_user.emails else None,
                roles=roles,
                joined_at=member_user.created_at,
                avatar_url=member_user.avatar_url,
                is_flow_employee=member_is_employee,
                flow_id=require_flow_employee_flow_id(member_user) if member_is_employee else None,
                curator_user_ids=flow_employee_curator_user_ids(member_user) if member_is_employee else [],
            )
        )
    return ListResponse[TeamMemberResponse](items=members)
