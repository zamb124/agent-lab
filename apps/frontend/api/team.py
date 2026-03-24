"""
API для управления командой компании
"""
import logging
from typing import List
from fastapi import APIRouter, HTTPException, Request
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import TeamMemberInfo, TeamInvite, TeamMemberUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/team", tags=["team"])


@router.get("/members", response_model=List[TeamMemberInfo])
async def get_team_members(request: Request, container: ContainerDep):
    """
    Получить список участников команды
    
    Returns:
        Список участников с их ролями
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    user_repo = container.user_repository
    
    members = []
    for user_id, roles in company.members.items():
        member_user = await user_repo.get(user_id)
        if member_user:
            members.append(TeamMemberInfo(
                user_id=user_id,
                name=member_user.name,
                email=None,  # Email храним в provider mapping
                roles=roles if isinstance(roles, list) else [roles],
                joined_at=member_user.created_at,
                avatar_url=member_user.avatar_url,
            ))
    
    return members


@router.post("/invite")
async def invite_member(
    invite: TeamInvite,
    request: Request,
    container: ContainerDep
):
    """
    Пригласить нового участника в команду
    
    Args:
        invite: Данные приглашения (email + role)
    
    Returns:
        Информация о приглашении
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    if 'owner' not in company.members.get(user.user_id, []) and \
       'admin' not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    valid_roles = ['owner', 'admin', 'developer', 'viewer']
    if invite.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимая роль. Допустимые: {', '.join(valid_roles)}"
        )
    
    # TODO: Реализовать систему приглашений через email
    # Пока возвращаем заглушку
    logger.info(f"Приглашение отправлено на {invite.email} с ролью {invite.role}")
    
    return {
        "success": True,
        "message": f"Приглашение отправлено на {invite.email}",
        "email": invite.email,
        "role": invite.role
    }


@router.patch("/members/{user_id}")
async def update_member_role(
    user_id: str,
    update: TeamMemberUpdate,
    request: Request,
    container: ContainerDep
):
    """
    Изменить роли участника команды
    
    Args:
        user_id: ID пользователя
        update: Новые роли
    
    Returns:
        Обновленная информация об участнике
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    if 'owner' not in company.members.get(user.user_id, []) and \
       'admin' not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    if user_id not in company.members:
        raise HTTPException(status_code=404, detail="Участник не найден")
    
    if user_id == company.owner_user_id and 'owner' not in update.roles:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить роль owner у владельца компании"
        )
    
    valid_roles = ['owner', 'admin', 'developer', 'viewer']
    for role in update.roles:
        if role not in valid_roles:
            raise HTTPException(
                status_code=400,
                detail=f"Недопустимая роль: {role}"
            )
    
    company.members[user_id] = update.roles
    company_repo = container.company_repository
    await company_repo.set(company)
    
    user_repo = container.user_repository
    target_user = await user_repo.get(user_id)
    if target_user and company.company_id in target_user.companies:
        target_user.companies[company.company_id] = update.roles
        await user_repo.set(target_user)
    
    logger.info(f"Обновлены роли пользователя {user_id} в компании {company.company_id}")
    
    return {
        "success": True,
        "user_id": user_id,
        "roles": update.roles
    }


@router.delete("/members/{user_id}")
async def remove_member(
    user_id: str,
    request: Request,
    container: ContainerDep
):
    """
    Удалить участника из команды
    
    Args:
        user_id: ID пользователя
    
    Returns:
        Результат удаления
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    if 'owner' not in company.members.get(user.user_id, []) and \
       'admin' not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    if user_id not in company.members:
        raise HTTPException(status_code=404, detail="Участник не найден")
    
    if user_id == company.owner_user_id:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить владельца компании"
        )
    
    del company.members[user_id]
    company_repo = container.company_repository
    await company_repo.set(company)
    
    user_repo = container.user_repository
    target_user = await user_repo.get(user_id)
    if target_user and company.company_id in target_user.companies:
        del target_user.companies[company.company_id]
        if target_user.active_company_id == company.company_id:
            target_user.active_company_id = list(target_user.companies.keys())[0] if target_user.companies else ""
        await user_repo.set(target_user)
    
    logger.info(f"Удален участник {user_id} из компании {company.company_id}")
    
    return {
        "success": True,
        "message": "Участник удален из команды"
    }
