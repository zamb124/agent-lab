"""
API для настроек компании
"""
import logging

from fastapi import APIRouter, HTTPException, Request

from core.config import get_settings
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import CompanySettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])
_RAG_EMBEDDING_OVERRIDE_KEY = "rag_embedding_override"
_RAG_EMBEDDING_ALLOWED_PROVIDERS = {"openrouter", "provider_litserve"}


@router.get("/company")
async def get_company_settings(request: Request, container: ContainerDep):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    company = request.state.company
    settings = get_settings()
    default_provider = settings.rag.embedding.provider
    default_model = settings.rag.embedding.api.model
    override_raw = company.metadata.get(_RAG_EMBEDDING_OVERRIDE_KEY)
    override_provider = None
    override_model = None
    if override_raw is not None:
        if not isinstance(override_raw, dict):
            raise HTTPException(status_code=500, detail="Некорректный формат rag embedding override в metadata")
        override_provider_raw = override_raw.get("provider")
        override_model_raw = override_raw.get("model")
        if not isinstance(override_provider_raw, str) or override_provider_raw not in _RAG_EMBEDDING_ALLOWED_PROVIDERS:
            raise HTTPException(status_code=500, detail="Некорректный provider в rag embedding override")
        if not isinstance(override_model_raw, str) or not override_model_raw.strip():
            raise HTTPException(status_code=500, detail="Некорректная модель в rag embedding override")
        override_provider = override_provider_raw
        override_model = override_model_raw.strip()

    effective_provider = override_provider if override_provider is not None else default_provider
    effective_model = override_model if override_model is not None else default_model

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
        "rag_embedding": {
            "enabled": override_provider is not None,
            "default_provider": default_provider,
            "default_model": default_model,
            "provider": effective_provider,
            "model": effective_model,
        },
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

    if update.rag_embedding is not None:
        if update.rag_embedding.enabled:
            provider = update.rag_embedding.provider
            model = update.rag_embedding.model
            if provider is None or provider not in _RAG_EMBEDDING_ALLOWED_PROVIDERS:
                raise HTTPException(status_code=400, detail="Некорректный provider для rag embedding")
            if model is None or not model.strip():
                raise HTTPException(status_code=400, detail="Модель для rag embedding обязательна")
            company.metadata[_RAG_EMBEDDING_OVERRIDE_KEY] = {
                "provider": provider,
                "model": model.strip(),
            }
        else:
            company.metadata.pop(_RAG_EMBEDDING_OVERRIDE_KEY, None)
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
