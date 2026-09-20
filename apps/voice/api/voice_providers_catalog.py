"""
Публичный каталог доступных моделей речи для Console (без секретов и без чтения ключей из conf).
Любой авторизованный пользователь платформы.

``GET /voice/api/v1/voice-providers/catalog``: роутер в ``pages_routers``. Путь должен быть
в ``core/middleware/auth/route_config.py::ROUTE_RULES`` и при необходимости в ``NO_SUBDOMAIN_ALLOWED_PATHS``,
иначе AuthMiddleware вернёт 404 до FastAPI (префикс ``/frontend/`` исключён из SPA-fallback).
"""

from __future__ import annotations

from fastapi import APIRouter

from apps.voice.dependencies import ContainerDep
from core.context import require_context
from core.models.voice_providers_catalog import (
    VoiceProvidersCatalogDTO,
    VoiceProvidersCatalogPayload,
    op_voice_providers_catalog,
)

router = APIRouter(prefix="/api/v1/voice-providers", tags=["voice"])


@router.get("/catalog", response_model=VoiceProvidersCatalogDTO)
async def voice_providers_catalog(container: ContainerDep) -> VoiceProvidersCatalogDTO:
    return await op_voice_providers_catalog(
        VoiceProvidersCatalogPayload(),
        user=require_context().user,
        container=container,
    )
