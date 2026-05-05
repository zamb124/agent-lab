"""Каталог и правила ключей secrets для провайдеров речи (Console API)."""

from __future__ import annotations

from typing import FrozenSet

from pydantic import BaseModel, ConfigDict, Field

from core.clients.speech_provider_catalog import (
    STT_TTS_PROVIDER_IDS,
    VOICE_RESPONSE_FORMAT_IDS,
)

_CLOUD_RU_STT_MODELS: tuple[str, ...] = (
    "openai/whisper-large-v3",
)
_CLOUD_RU_TTS_MODELS: tuple[str, ...] = (
    "openai/tts-1",
    "openai/tts-1-hd",
)
_YANDEX_SPEECH_MODELS: tuple[str, ...] = ("general",)
_SBER_SPEECH_MODELS: tuple[str, ...] = ("general",)


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


class TtsLitserveVoiceHint(BaseModel):
    """Подсказка по голосу для одной Litserve TTS-модели."""

    model_config = ConfigDict(extra="forbid")

    api_model_id: str
    default_voice: str | None = None


class VoiceProvidersCatalogDTO(BaseModel):
    """Ответ GET .../voice-providers/catalog (без конфиденциальных данных из conf)."""

    model_config = ConfigDict(extra="forbid")

    stt_tts_provider_ids: list[str] = Field(default_factory=list)
    response_format_ids: list[str] = Field(default_factory=list)
    credential_field_groups: dict[str, list[list[str]]] = Field(default_factory=dict)
    stt_litserve_models: list[str] = Field(default_factory=list)
    tts_litserve_models: list[str] = Field(default_factory=list)
    tts_litserve_voice_hints: list[TtsLitserveVoiceHint] = Field(default_factory=list)
    cloud_ru_stt_models: list[str] = Field(default_factory=list)
    cloud_ru_tts_models: list[str] = Field(default_factory=list)
    yandex_speech_models: list[str] = Field(default_factory=list)
    sber_speech_models: list[str] = Field(default_factory=list)


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


def cloud_ru_stt_model_ids() -> list[str]:
    return list(_CLOUD_RU_STT_MODELS)


def cloud_ru_tts_model_ids() -> list[str]:
    return list(_CLOUD_RU_TTS_MODELS)


def catalog_yandex_speech_models() -> list[str]:
    return list(_YANDEX_SPEECH_MODELS)


def catalog_sber_speech_models() -> list[str]:
    return list(_SBER_SPEECH_MODELS)


def build_voice_providers_catalog_dto(pls_settings: object) -> VoiceProvidersCatalogDTO:
    """Собирает каталог только из уже разрешённых полей конфига."""

    credential_field_groups: dict[str, list[list[str]]] = {
        "cloud_ru": [["api_key"]],
        "yandex": [["api_key"], ["folder_id"]],
        "sber": [["client_id"], ["client_secret"], ["scope"]],
    }

    def _pull_ids(getter: object, field: str = "api_model_id") -> list[str]:
        items = getter
        ident: list[str] = []
        for entry in items:
            v = getattr(entry, field)
            ident.append(str(v))
        return ident

    pls_any = pls_settings
    stt_models = getattr(pls_any, "stt_models", [])
    tts_models = getattr(pls_any, "tts_models", [])
    voice_hints = [
        TtsLitserveVoiceHint(
            api_model_id=str(tts.api_model_id),
            default_voice=tts.voice if hasattr(tts, "voice") else None,
        )
        for tts in tts_models
    ]

    return VoiceProvidersCatalogDTO(
        stt_tts_provider_ids=sorted(STT_TTS_PROVIDER_IDS),
        response_format_ids=sorted(VOICE_RESPONSE_FORMAT_IDS),
        credential_field_groups=credential_field_groups,
        stt_litserve_models=_pull_ids(stt_models),
        tts_litserve_models=_pull_ids(tts_models),
        tts_litserve_voice_hints=voice_hints,
        cloud_ru_stt_models=cloud_ru_stt_model_ids(),
        cloud_ru_tts_models=cloud_ru_tts_model_ids(),
        yandex_speech_models=catalog_yandex_speech_models(),
        sber_speech_models=catalog_sber_speech_models(),
    )
