"""
Публичный каталог доступных моделей речи для Console (без секретов и без чтения ключей из conf).
Любой авторизованный пользователь платформы.

``GET /voice/api/v1/voice-providers/catalog``: роутер в ``pages_routers``. Путь покрыт правилом
``/voice/api/v1/*`` в ``core/middleware/auth/route_config.py::ROUTE_RULES`` и входит в
``NO_SUBDOMAIN_ALLOWED_PATHS`` (консоль без субдомена компании).
"""

from __future__ import annotations

from fastapi import APIRouter

from apps.voice.di import Di
from core.context import require_context
from core.models.voice_providers_catalog import (
    VoiceProvidersCatalogDTO,
    VoiceProvidersCatalogPayload,
)
from core.voice.operations import op_voice_providers_catalog

router = APIRouter(prefix="/api/v1/voice-providers", tags=["voice"])


@router.get("/catalog", response_model=VoiceProvidersCatalogDTO)
async def voice_providers_catalog(di: Di) -> VoiceProvidersCatalogDTO:
    return await op_voice_providers_catalog(
        VoiceProvidersCatalogPayload(),
        user=require_context().user,
        di=di,
    )
