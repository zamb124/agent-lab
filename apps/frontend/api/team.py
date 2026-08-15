"""
API для управления командой компании.

GET /members перенесён в core/api/team.py (доступен во всех сервисах).
"""

from fastapi import APIRouter, HTTPException

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    TeamMemberRemoveResponse,
    TeamMemberRoleUpdateResponse,
    TeamMemberUpdate,
)
from core.context import require_context
from core.identity.company_membership import (
    remove_company_membership,
    set_company_member_roles,
)
from core.logging import get_logger
from core.models.identity_models import Company, User

logger = get_logger(__name__)
router = APIRouter(prefix="/api/team", tags=["team"])


def _require_team_principal() -> tuple[User, Company]:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return context.user, company


async def _require_team_admin(container: ContainerDep) -> tuple[User, Company]:
    user, company = _require_team_principal()
    await container.authz_service.require_company_admin(
        company_id=company.company_id,
        user_id=user.user_id,
    )
    return user, company


@router.patch("/members/{user_id}", response_model=TeamMemberRoleUpdateResponse)
async def update_member_role(
    user_id: str,
    update: TeamMemberUpdate,
    container: ContainerDep,
) -> TeamMemberRoleUpdateResponse:
    _, company = await _require_team_admin(container)
    if user_id not in company.members:
        raise HTTPException(status_code=404, detail="Участник не найден")

    if user_id == company.owner_user_id and "owner" not in update.roles:
        raise HTTPException(status_code=400, detail="Нельзя удалить роль owner у владельца компании")

    valid_roles = {"owner", "admin", "developer", "viewer"}
    for role in update.roles:
        if role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Недопустимая роль: {role}")

    target_user = await container.user_repository.get(user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    roles = await set_company_member_roles(
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        authz=container.authz_service,
        company=company,
        user=target_user,
        roles=update.roles,
    )

    logger.info("Обновлены роли пользователя %s в компании %s", user_id, company.company_id)

    return TeamMemberRoleUpdateResponse(user_id=user_id, roles=roles)


@router.delete("/members/{user_id}", response_model=TeamMemberRemoveResponse)
async def remove_member(
    user_id: str,
    container: ContainerDep,
) -> TeamMemberRemoveResponse:
    _, company = await _require_team_admin(container)
    if user_id not in company.members:
        raise HTTPException(status_code=404, detail="Участник не найден")

    if user_id == company.owner_user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить владельца компании")

    target_user = await container.user_repository.get(user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    await remove_company_membership(
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        authz=container.authz_service,
        company=company,
        user=target_user,
    )

    logger.info("Удален участник %s из компании %s", user_id, company.company_id)

    return TeamMemberRemoveResponse(message="Участник удален из команды")
