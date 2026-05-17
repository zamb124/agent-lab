"""DTO и сборка каталога провайдеров речи (общие для frontend и flows)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.clients.speech_provider_catalog import (
    BASE_SPEECH_LANGUAGE_IDS,
    CLOUD_RU_OPENAI_TTS_VOICE_IDS,
    LITSERVE_SILERO_TTS_SAMPLE_RATE_IDS,
    SBER_TTS_VOICE_IDS,
    STT_TTS_PROVIDER_IDS,
    TTS_SAMPLE_RATE_IDS,
    VAD_PROVIDER_IDS,
    VAD_SAMPLE_RATE_BASE_IDS,
    VOICE_RESPONSE_FORMAT_IDS,
    YANDEX_TTS_VOICE_IDS,
    catalog_sber_speech_models,
    catalog_yandex_speech_models,
    cloud_ru_stt_model_ids,
    cloud_ru_tts_model_ids,
)
from core.config.models import SILERO_V5_RU_SPEAKERS_BY_BUNDLE


class TtsLitserveVoiceHint(BaseModel):
    """Подсказка по голосу для одной Litserve TTS-модели."""

    model_config = ConfigDict(extra="forbid")

    api_model_id: str
    default_voice: str | None = None
    voice_ids: list[str] = Field(default_factory=list)


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
    speech_language_ids: list[str] = Field(default_factory=list)
    vad_provider_ids: list[str] = Field(default_factory=list)
    tts_sample_rate_ids: list[int] = Field(default_factory=list)
    vad_sample_rate_ids: list[int] = Field(default_factory=list)
    litserve_silero_tts_sample_rate_ids: list[int] = Field(default_factory=list)
    cloud_ru_tts_voice_ids: list[str] = Field(default_factory=list)
    yandex_tts_voice_ids: list[str] = Field(default_factory=list)
    sber_tts_voice_ids: list[str] = Field(default_factory=list)


def build_voice_providers_catalog_dto(pls_settings: object) -> VoiceProvidersCatalogDTO:
    """Собирает каталог: статические allowlist из speech_provider_catalog, Litserve из conf."""

    def _nested_models(pls_any: object, name: str) -> list[object]:
        infra = getattr(pls_any, "infra", None)
        if infra is not None:
            inner = getattr(infra, name, None)
            if isinstance(inner, list):
                return list(inner)
        direct = getattr(pls_any, name, None)
        return list(direct) if isinstance(direct, list) else []

    credential_field_groups: dict[str, list[list[str]]] = {
        "cloud_ru": [["api_key"]],
        "yandex": [["api_key"], ["folder_id"]],
        "sber": [["client_id"], ["client_secret"], ["scope"]],
    }

    def _pull_ids(items: list[object], field: str = "api_model_id") -> list[str]:
        ident: list[str] = []
        for entry in items:
            v = getattr(entry, field, None)
            if v is None:
                continue
            ident.append(str(v))
        return ident

    pls_any = pls_settings
    stt_models = _nested_models(pls_any, "stt_models")
    tts_models = _nested_models(pls_any, "tts_models")
    voice_hints: list[TtsLitserveVoiceHint] = []
    for tts in tts_models:
        api_model_id = getattr(tts, "api_model_id", None)
        if api_model_id is None:
            continue
        bundle_raw = getattr(tts, "silero_bundle", None)
        bundle = str(bundle_raw).strip().lower() if bundle_raw is not None else ""
        allowed = SILERO_V5_RU_SPEAKERS_BY_BUNDLE.get(bundle, frozenset())
        voice_ids = sorted(allowed) if allowed else []
        voice = getattr(tts, "voice", None)
        voice_hints.append(
            TtsLitserveVoiceHint(
                api_model_id=str(api_model_id),
                default_voice=voice if isinstance(voice, str) else None,
                voice_ids=voice_ids,
            )
        )

    speech_langs: set[str] = set(BASE_SPEECH_LANGUAGE_IDS)
    for tts in tts_models:
        loc = getattr(tts, "synthesis_locale", None)
        if loc is None:
            continue
        if not isinstance(loc, str):
            continue
        base = loc.strip().lower().split("-")[0].split("_")[0]
        if len(base) >= 2:
            speech_langs.add(base[:2])

    vad_rates: set[int] = set(VAD_SAMPLE_RATE_BASE_IDS)
    vad_models = _nested_models(pls_any, "vad_models")
    for vad in vad_models:
        sr = getattr(vad, "sample_rate", None)
        if sr is not None:
            vad_rates.add(int(sr))

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
        speech_language_ids=sorted(speech_langs),
        vad_provider_ids=sorted(VAD_PROVIDER_IDS),
        tts_sample_rate_ids=list(TTS_SAMPLE_RATE_IDS),
        vad_sample_rate_ids=sorted(vad_rates),
        litserve_silero_tts_sample_rate_ids=list(LITSERVE_SILERO_TTS_SAMPLE_RATE_IDS),
        cloud_ru_tts_voice_ids=list(CLOUD_RU_OPENAI_TTS_VOICE_IDS),
        yandex_tts_voice_ids=list(YANDEX_TTS_VOICE_IDS),
        sber_tts_voice_ids=list(SBER_TTS_VOICE_IDS),
    )
