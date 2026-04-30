"""
API для управления командой компании.

GET /members перенесён в core/api/team.py (доступен во всех сервисах).
"""

from core.logging import get_logger
from fastapi import APIRouter, HTTPException, Request

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import TeamMemberUpdate

logger = get_logger(__name__)
router = APIRouter(prefix="/api/team", tags=["team"])

@router.patch("/members/{user_id}")
async def update_member_role(
    user_id: str,
    update: TeamMemberUpdate,
    request: Request,
    container: ContainerDep,
):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    user = request.state.user
    company = request.state.company

    roles = company.members.get(user.user_id, [])
    if "owner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if user_id not in company.members:
        raise HTTPException(status_code=404, detail="Участник не найден")

    if user_id == company.owner_user_id and "owner" not in update.roles:
        raise HTTPException(status_code=400, detail="Нельзя удалить роль owner у владельца компании")

    valid_roles = ["owner", "admin", "developer", "viewer"]
    for role in update.roles:
        if role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Недопустимая роль: {role}")

    company.members[user_id] = update.roles
    await container.company_repository.set(company)

    target_user = await container.user_repository.get(user_id)
    if target_user and company.company_id in target_user.companies:
        target_user.companies[company.company_id] = update.roles
        await container.user_repository.set(target_user)

    logger.info("Обновлены роли пользователя %s в компании %s", user_id, company.company_id)

    return {"success": True, "user_id": user_id, "roles": update.roles}

@router.delete("/members/{user_id}")
async def remove_member(
    user_id: str,
    request: Request,
    container: ContainerDep,
):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    user = request.state.user
    company = request.state.company

    roles = company.members.get(user.user_id, [])
    if "owner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if user_id not in company.members:
        raise HTTPException(status_code=404, detail="Участник не найден")

    if user_id == company.owner_user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить владельца компании")

    del company.members[user_id]
    await container.company_repository.set(company)

    target_user = await container.user_repository.get(user_id)
    if target_user and company.company_id in target_user.companies:
        del target_user.companies[company.company_id]
        if target_user.active_company_id == company.company_id:
            remaining = list(target_user.companies.keys())
            if not remaining:
                raise ValueError(f"Пользователь {user_id} не состоит ни в одной компании после удаления")
            target_user.active_company_id = remaining[0]
        await container.user_repository.set(target_user)

    logger.info("Удален участник %s из компании %s", user_id, company.company_id)

    return {"success": True, "message": "Участник удален из команды"}
