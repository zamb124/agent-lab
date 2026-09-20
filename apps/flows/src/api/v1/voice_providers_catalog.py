"""
Каталог провайдеров речи для UI редактора flow (тот же DTO и `op_*`, что frontend).
"""

from __future__ import annotations

from fastapi import APIRouter

from apps.flows.src.dependencies import ContainerDep
from core.context import require_context
from core.models.voice_providers_catalog import (
    VoiceProvidersCatalogDTO,
    VoiceProvidersCatalogPayload,
    op_voice_providers_catalog,
)

router = APIRouter(prefix="/voice-providers", tags=["flows", "voice"])


@router.get("/catalog", response_model=VoiceProvidersCatalogDTO)
async def flows_voice_providers_catalog(container: ContainerDep) -> VoiceProvidersCatalogDTO:
    return await op_voice_providers_catalog(
        VoiceProvidersCatalogPayload(),
        user=require_context().user,
        container=container,
    )
