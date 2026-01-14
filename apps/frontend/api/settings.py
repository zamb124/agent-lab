"""
API для настроек компании
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import CompanySettingsUpdate
from core.models.identity_models import AuthProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/company")
async def get_company_settings(request: Request, container: ContainerDep):
    """
    Получить настройки компании
    
    Returns:
        Настройки компании
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    company = request.state.company
    
    return {
        "company_id": company.company_id,
        "name": company.name,
        "subdomain": company.subdomain,
        "owner_user_id": company.owner_user_id,
        "status": company.status,
        "monthly_budget": company.monthly_budget,
        "tariff_plan": company.tariff_plan.value,
        "created_at": company.created_at.isoformat(),
        "metadata": company.metadata
    }


@router.patch("/company")
async def update_company_settings(
    update: CompanySettingsUpdate,
    request: Request,
    container: ContainerDep
):
    """
    Обновить настройки компании
    
    Args:
        update: Новые настройки
    
    Returns:
        Обновленные настройки
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
    
    updated = False
    
    if update.name is not None:
        company.name = update.name
        updated = True
    
    if update.monthly_budget is not None:
        if update.monthly_budget < 0:
            raise HTTPException(
                status_code=400,
                detail="Месячный лимит не может быть отрицательным"
            )
        company.monthly_budget = update.monthly_budget
        updated = True
    
    if update.metadata is not None:
        company.metadata.update(update.metadata)
        updated = True
    
    if updated:
        company_repo = container.company_repository
        await company_repo.set(company)
        logger.info(f"Обновлены настройки компании {company.company_id}")
    
    return {
        "success": True,
        "message": "Настройки обновлены",
        "company": {
            "name": company.name,
            "monthly_budget": company.monthly_budget,
            "metadata": company.metadata
        }
    }


@router.get("/security")
async def get_security_settings(request: Request, container: ContainerDep):
    """
    Получить настройки безопасности
    
    Returns:
        Настройки безопасности (сессии, OAuth)
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    user = request.state.user
    
    # TODO: Получить активные сессии из AuthSessionRepository
    active_sessions = []
    
    return {
        "user_id": user.user_id,
        "active_sessions": active_sessions,
        "two_factor_enabled": False,  # TODO: Реализовать двухфакторную аутентификацию
        "oauth_providers": ["yandex", "google", "github"]
    }


@router.get("/oauth-providers")
async def get_oauth_providers(request: Request, container: ContainerDep):
    """
    Получить список доступных OAuth провайдеров
    
    Returns:
        Список провайдеров с их статусом
    """
    providers = []
    
    for provider in AuthProvider:
        providers.append({
            "id": provider.value,
            "name": provider.value.capitalize(),
            "enabled": True,
            "icon": f"/static/frontend/assets/icons/providers/{provider.value}.svg"
        })
    
    return {
        "providers": providers
    }


@router.get("/integrations")
async def get_integrations(request: Request, container: ContainerDep):
    """
    Получить настройки интеграций
    
    Returns:
        Список подключенных интеграций
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    # TODO: Реализовать систему интеграций
    return {
        "integrations": [],
        "available": [
            {"id": "telegram", "name": "Telegram", "status": "available"},
            {"id": "slack", "name": "Slack", "status": "available"},
            {"id": "webhook", "name": "Webhooks", "status": "available"}
        ]
    }


