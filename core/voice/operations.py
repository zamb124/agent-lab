"""Команда каталога провайдеров речи для voice и flows."""

from __future__ import annotations

from core.config import get_settings
from core.di.platform import PlatformDi
from core.models.identity_models import User
from core.models.voice_providers_catalog import (
    VoiceProvidersCatalogDTO,
    VoiceProvidersCatalogPayload,
    build_voice_providers_catalog_dto,
)


async def op_voice_providers_catalog(
    payload: VoiceProvidersCatalogPayload,
    *,
    user: User,
    di: PlatformDi,
) -> VoiceProvidersCatalogDTO:
    _ = payload, user, di
    return build_voice_providers_catalog_dto(get_settings().provider_litserve)
