"""Каталог и правила ключей secrets для провайдеров речи (Console API)."""

from __future__ import annotations

from typing import FrozenSet

from pydantic import BaseModel, ConfigDict, Field

from core.clients.speech_provider_catalog import (
    catalog_sber_speech_models,
    catalog_yandex_speech_models,
    cloud_ru_stt_model_ids,
    cloud_ru_tts_model_ids,
)
from core.models.voice_providers_catalog import (
    TtsLitserveVoiceHint,
    VoiceProvidersCatalogDTO,
    build_voice_providers_catalog_dto,
)

__all__ = [
    "TtsLitserveVoiceHint",
    "VoiceProvidersCatalogDTO",
    "build_voice_providers_catalog_dto",
    "allowed_secret_keys",
    "needs_model_dropdown",
    "CompanySecretsMetaDTO",
    "secrets_dict_to_meta",
    "cloud_ru_stt_model_ids",
    "cloud_ru_tts_model_ids",
    "catalog_yandex_speech_models",
    "catalog_sber_speech_models",
]


def allowed_secret_keys(kind: str, provider: str) -> FrozenSet[str]:
    """Допустимые ключи в JSONB secrets для связки kind + provider."""
    _ = kind
    if provider == "litserve" or provider == "silero_local" or provider == "mock":
        return frozenset()
    if provider == "cloud_ru":
        return frozenset({"api_key"})
    if provider == "yandex":
        return frozenset({"api_key", "folder_id"})
    if provider == "sber":
        return frozenset({"client_id", "client_secret", "scope"})
    raise ValueError(f"Неизвестный provider для secrets: {provider!r}")


def needs_model_dropdown(kind: str, provider: str) -> bool:
    _ = kind
    if provider in ("silero_local", "mock"):
        return False
    return provider in {"litserve", "cloud_ru", "yandex", "sber"}


class CompanySecretsMetaDTO(BaseModel):
    """Не выдаёт сырое значение api_key/client_secret."""

    model_config = ConfigDict(extra="forbid")

    api_key_set: bool | None = None
    client_secret_set: bool | None = None
    folder_id: str | None = None
    client_id: str | None = None
    scope: str | None = None


def secrets_dict_to_meta(
    *,
    secrets: dict[str, object] | None,
    provider: str,
) -> CompanySecretsMetaDTO | None:
    if secrets is None or len(secrets) == 0:
        return CompanySecretsMetaDTO()
    ak = secrets.get("api_key")
    api_key_set: bool | None = isinstance(ak, str) and ak != ""

    cs = secrets.get("client_secret")
    client_secret_set = isinstance(cs, str) and cs != ""

    folder_id_val = secrets.get("folder_id")
    folder_id: str | None = folder_id_val if isinstance(folder_id_val, str) and folder_id_val != "" else None

    client_id_val = secrets.get("client_id")
    client_id: str | None = client_id_val if isinstance(client_id_val, str) and client_id_val != "" else None

    scope_val = secrets.get("scope")
    scope: str | None = scope_val if isinstance(scope_val, str) and scope_val != "" else None

    if provider == "cloud_ru":
        return CompanySecretsMetaDTO(api_key_set=api_key_set)
    if provider == "yandex":
        return CompanySecretsMetaDTO(api_key_set=api_key_set, folder_id=folder_id)
    if provider == "sber":
        return CompanySecretsMetaDTO(
            client_secret_set=client_secret_set,
            client_id=client_id,
            scope=scope,
        )
    return None
