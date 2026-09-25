"""
Каталог провайдеров речи для UI редактора flow (тот же DTO и `op_*`, что frontend).
"""

from __future__ import annotations

from fastapi import APIRouter

from apps.flows.di import Di
from core.context import require_context
from core.models.voice_providers_catalog import (
    VoiceProvidersCatalogDTO,
    VoiceProvidersCatalogPayload,
)
from core.voice.operations import op_voice_providers_catalog

router = APIRouter(prefix="/voice-providers", tags=["flows", "voice"])


@router.get("/catalog", response_model=VoiceProvidersCatalogDTO)
async def flows_voice_providers_catalog(di: Di) -> VoiceProvidersCatalogDTO:
    return await op_voice_providers_catalog(
        VoiceProvidersCatalogPayload(),
        user=require_context().user,
        di=di,
    )
