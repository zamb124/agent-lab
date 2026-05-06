"""
Каталог провайдеров речи для UI редактора flow (тот же DTO, что GET /frontend/api/voice-providers/catalog).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from apps.flows.src.dependencies import ContainerDep
from core.config import get_settings
from core.logging import get_logger
from core.models.identity_models import User
from core.models.voice_providers_catalog import (
    VoiceProvidersCatalogDTO,
    build_voice_providers_catalog_dto,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/voice-providers", tags=["flows", "voice"])


def _require_authenticated_user(request: Request) -> User:
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return request.state.user


@router.get("/catalog", response_model=VoiceProvidersCatalogDTO)
async def flows_voice_providers_catalog(request: Request, container: ContainerDep) -> VoiceProvidersCatalogDTO:
    _ = container
    _require_authenticated_user(request)
    pls = get_settings().provider_litserve
    return build_voice_providers_catalog_dto(pls)
