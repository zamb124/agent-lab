"""Команда списка участников компании — общая для консоли (`frontend/team/list_requested`),
Documents (`office/company_members/list_requested`) и REST `GET /{svc}/api/team/members`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.di.platform import PlatformDi
from core.errors.boundary import PlatformNotFoundError
from core.identity.flow_employee import (
    flow_employee_curator_user_ids,
    is_flow_employee,
    require_flow_employee_flow_id,
)
from core.models.base import StrictBaseModel
from core.models.identity_models import Company, User
from core.pagination import OffsetPage
from core.request_scope import require_company_viewer
from core.websocket import Operation


class TeamMembersListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


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
    payload: TeamMembersListPayload, *, user: User, di: PlatformDi
) -> OffsetPage[TeamMemberResponse]:
    """Roster активной компании с признаками flow-сотрудников; Check `company` viewer."""
    _ = user
    scope = await require_company_viewer(di.authz_service)
    company = await Company.get(scope.company_id)
    if company is None:
        raise PlatformNotFoundError(f"Company {scope.company_id} not found", error_code="not_found")
    users_by_id = await User.get_many(list(company.members.keys()))
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
    return OffsetPage[TeamMemberResponse](
        items=members[payload.offset : payload.offset + payload.limit],
        total=len(members),
        limit=payload.limit,
        offset=payload.offset,
    )


TEAM_MEMBERS_LIST_OPERATION: Operation[TeamMembersListPayload, PlatformDi] = Operation(
    payload_model=TeamMembersListPayload, fn=op_team_members_list
)
