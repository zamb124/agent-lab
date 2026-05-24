"""
Публичный каталог доступных моделей речи для Console (без секретов и без чтения ключей из conf).
Любой авторизованный пользователь платформы.

``GET /frontend/api/voice-providers/catalog``: роутер в ``pages_routers``. Путь должен быть
в ``core/middleware/auth/route_config.py::ROUTE_RULES`` и при необходимости в ``NO_SUBDOMAIN_ALLOWED_PATHS``,
иначе AuthMiddleware вернёт 404 до FastAPI (префикс ``/frontend/`` исключён из SPA-fallback).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.frontend.api.voice_providers_catalog_helpers import (
    VoiceProvidersCatalogDTO,
    build_voice_providers_catalog_dto,
)
from apps.frontend.dependencies import ContainerDep
from core.config import get_settings
from core.context import get_context
from core.models.identity_models import User

router = APIRouter(prefix="/api/voice-providers", tags=["frontend", "voice"])


def _require_authenticated_user() -> User:
    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return context.user


@router.get("/catalog", response_model=VoiceProvidersCatalogDTO)
async def voice_providers_catalog(container: ContainerDep) -> VoiceProvidersCatalogDTO:
    _ = container
    _ = _require_authenticated_user()
    pls = get_settings().provider_litserve
    return build_voice_providers_catalog_dto(pls)
