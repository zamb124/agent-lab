"""API для базовых настроек компании.

AI-провайдеры (capabilities + custom OpenAI-compatible) — отдельный роутер
[`apps/frontend/api/ai_providers.py`](apps/frontend/api/ai_providers.py).
"""

from fastapi import APIRouter, HTTPException

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    CompanySettingsResponse,
    CompanySettingsUpdate,
    CompanySettingsUpdatedCompany,
    CompanySettingsUpdateResponse,
)
from core.context import require_context
from core.logging import get_logger
from core.models.identity_models import Company, User

logger = get_logger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


def _require_settings_principal() -> tuple[User, Company]:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return context.user, company


def _require_settings_admin() -> tuple[User, Company]:
    user, company = _require_settings_principal()
    roles = company.members.get(user.user_id, [])
    if "owner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user, company


@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings() -> CompanySettingsResponse:
    _, company = _require_settings_principal()
    return CompanySettingsResponse(
        company_id=company.company_id,
        name=company.name,
        subdomain=company.subdomain,
        owner_user_id=company.owner_user_id,
        status=company.status,
        monthly_budget=company.monthly_budget,
        tariff_plan=company.tariff_plan.value,
        created_at=company.created_at.isoformat(),
        metadata=company.metadata,
    )


@router.patch("/company", response_model=CompanySettingsUpdateResponse)
async def update_company_settings(
    update: CompanySettingsUpdate,
    container: ContainerDep,
) -> CompanySettingsUpdateResponse:
    _, company = _require_settings_admin()
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
        _ = await company_repo.set(company)
        logger.info("Обновлены настройки компании %s", company.company_id)

    return CompanySettingsUpdateResponse(
        message="Настройки обновлены",
        company=CompanySettingsUpdatedCompany(
            name=company.name,
            monthly_budget=company.monthly_budget,
            metadata=company.metadata,
        ),
    )
