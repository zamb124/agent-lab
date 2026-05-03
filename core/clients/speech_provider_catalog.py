"""Единые множества имён провайдеров речи для валидации API и конфигов."""

from __future__ import annotations

STT_TTS_PROVIDER_IDS: frozenset[str] = frozenset(
    {"litserve", "cloud_ru", "yandex", "sber", "mock"}
)
VAD_PROVIDER_IDS: frozenset[str] = frozenset({"litserve", "silero_local", "mock"})
VOICE_RESPONSE_FORMAT_IDS: frozenset[str] = frozenset(
    {"wav", "mp3", "ogg", "pcm", "lpcm"}
)
