"""Единые множества имён провайдеров речи для валидации API и конфигов.

Allowlist идентификаторов моделей для UI (`VoiceProvidersCatalogDTO`) и для
`company_voice_providers` (валидация override) живут здесь же, не в сервисе
`apps/voice`: voice-процесс использует те же `settings.voice` и
`core.clients.voice_resolver`. При добавлении модели в STT/TTS клиенты —
расширять соответствующий кортеж в этом файле.

Дополнительно: языки (`BASE_SPEECH_LANGUAGE_IDS`), частоты TTS/VAD, голоса
облачных TTS (`CLOUD_RU_OPENAI_TTS_VOICE_IDS`, `YANDEX_TTS_VOICE_IDS`,
`SBER_TTS_VOICE_IDS`) для каталога UI редактора flow и консоли.
"""

from __future__ import annotations

STT_TTS_PROVIDER_IDS: frozenset[str] = frozenset(
    {"litserve", "cloud_ru", "yandex", "sber", "mock"}
)
VAD_PROVIDER_IDS: frozenset[str] = frozenset({"litserve", "silero_local", "mock"})
VOICE_RESPONSE_FORMAT_IDS: frozenset[str] = frozenset(
    {"wav", "mp3", "ogg", "pcm", "lpcm"}
)

# Языки для полей STT/TTS `language` в UI каталога (ISO 639-1): базовый набор +
# пополнение из synthesis_locale моделей LitServe при сборке DTO.
BASE_SPEECH_LANGUAGE_IDS: tuple[str, ...] = ("ru", "en")

# Частоты дискретизации TTS в UI (Гц); подмножество для Silero ru v5 в LitServe —
# см. ``litserve_silero_tts_sample_rate_ids`` в VoiceProvidersCatalogDTO.
TTS_SAMPLE_RATE_IDS: tuple[int, ...] = (8000, 16000, 24000, 44100, 48000)

LITSERVE_SILERO_TTS_SAMPLE_RATE_IDS: tuple[int, ...] = (8000, 24000, 48000)

# VAD silero_local (в процессе): только 8000 / 16000 Гц; LitServe VAD — также из vad_models conf.
VAD_SAMPLE_RATE_BASE_IDS: tuple[int, ...] = (8000, 16000)

# OpenAI-совместимый TTS (Cloud.ru tts-1 / tts-1-hd и аналоги).
CLOUD_RU_OPENAI_TTS_VOICE_IDS: tuple[str, ...] = (
    "alloy",
    "ash",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
)

# Yandex SpeechKit TTS (клиент пока stub): публичные имена голосов для UI allowlist.
YANDEX_TTS_VOICE_IDS: tuple[str, ...] = (
    "alena",
    "filipp",
    "ermil",
    "jane",
    "madirus",
    "omazh",
    "zahar",
)

# Sber SmartSpeech TTS (клиент пока stub): типичные идентификаторы голосов.
SBER_TTS_VOICE_IDS: tuple[str, ...] = (
    "May_24000",
    "Tur_24000",
    "Bys_24000",
    "Ost_24000",
    "Pon_24000",
)

# Cloud.ru Foundation Models API (см. CloudRuSTTConfig / CloudRuTTSBackendConfig).
CLOUD_RU_STT_API_MODEL_IDS: tuple[str, ...] = ("openai/whisper-large-v3",)
CLOUD_RU_TTS_API_MODEL_IDS: tuple[str, ...] = (
    "openai/tts-1",
    "openai/tts-1-hd",
)

# Yandex SpeechKit / Sber SmartSpeech: допустимые значения поля model в override
# до реализации полноценных REST-клиентов (см. YandexSTTBackendConfig.model).
YANDEX_SPEECH_MODEL_IDS: tuple[str, ...] = ("general",)
SBER_SPEECH_MODEL_IDS: tuple[str, ...] = ("general",)


def cloud_ru_stt_model_ids() -> list[str]:
    return list(CLOUD_RU_STT_API_MODEL_IDS)


def cloud_ru_tts_model_ids() -> list[str]:
    return list(CLOUD_RU_TTS_API_MODEL_IDS)


def catalog_yandex_speech_models() -> list[str]:
    return list(YANDEX_SPEECH_MODEL_IDS)


def catalog_sber_speech_models() -> list[str]:
    return list(SBER_SPEECH_MODEL_IDS)
