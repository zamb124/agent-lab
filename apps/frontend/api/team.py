"""REST-зеркало команд `frontend/team/*`. GET /members — `core/api/team.py` (во всех сервисах)."""

from fastapi import APIRouter

from apps.frontend.di import Di
from apps.frontend.models import (
    TeamMemberRemoveResponse,
    TeamMemberRoleUpdateResponse,
    TeamMemberUpdate,
)
from apps.frontend.realtime.company_operations import (
    TeamMemberIdPayload,
    TeamMemberRolesUpdatePayload,
    op_team_member_remove,
    op_team_member_roles_update,
)
from core.context import require_context

router = APIRouter(prefix="/api/team", tags=["team"])


@router.patch("/members/{user_id}", response_model=TeamMemberRoleUpdateResponse)
async def update_member_role(
    user_id: str,
    update: TeamMemberUpdate,
    di: Di,
) -> TeamMemberRoleUpdateResponse:
    return await op_team_member_roles_update(
        TeamMemberRolesUpdatePayload(user_id=user_id, roles=update.roles),
        user=require_context().user,
        di=di,
    )


@router.delete("/members/{user_id}", response_model=TeamMemberRemoveResponse)
async def remove_member(user_id: str, di: Di) -> TeamMemberRemoveResponse:
    return await op_team_member_remove(
        TeamMemberIdPayload(user_id=user_id), user=require_context().user, di=di
    )
