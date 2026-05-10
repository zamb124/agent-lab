"""API для базовых настроек компании.

AI-провайдеры (capabilities + custom OpenAI-compatible) — отдельный роутер
[`apps/frontend/api/ai_providers.py`](apps/frontend/api/ai_providers.py).
"""

from fastapi import APIRouter, HTTPException, Request

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import CompanySettingsUpdate
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/company")
async def get_company_settings(request: Request, container: ContainerDep):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
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
        "metadata": company.metadata,
    }


@router.patch("/company")
async def update_company_settings(
    update: CompanySettingsUpdate,
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

    updated = False

    if update.name is not None:
        company.name = update.name
        updated = True

    if update.monthly_budget is not None:
        if update.monthly_budget < 0:
            raise HTTPException(status_code=400, detail="Месячный лимит не может быть отрицательным")
        company.monthly_budget = update.monthly_budget
        updated = True

    if update.metadata is not None:
        company.metadata.update(update.metadata)
        updated = True

    if updated:
        company_repo = container.company_repository
        await company_repo.set(company)
        logger.info("Обновлены настройки компании %s", company.company_id)

    return {
        "success": True,
        "message": "Настройки обновлены",
        "company": {
            "name": company.name,
            "monthly_budget": company.monthly_budget,
            "metadata": company.metadata,
        },
    }
