"""Конфигурация voice сервиса.

`VoiceServiceSettings` наследует `BaseSettings` — отсюда же приходит
`settings.voice: SpeechProvidersConfig` (deployment-default для STT/TTS/VAD).
В этом классе остаются только voice-специфичные блоки `barge_in` и
`queue` для real-time WS-сессии.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from core.config import BaseSettings
from core.config.models import (
    VoiceBargeInSettings,
    VoiceQueueSettings,
)


class VoiceServiceSettings(BaseSettings):
    """Настройки voice сервиса (real-time WS-сессии)."""

    barge_in: VoiceBargeInSettings = Field(default_factory=VoiceBargeInSettings)
    queue: VoiceQueueSettings = Field(default_factory=VoiceQueueSettings)


_voice_settings: Optional[VoiceServiceSettings] = None


def get_voice_settings() -> VoiceServiceSettings:
    global _voice_settings
    if _voice_settings is None:
        from core.config.loader import load_merged_config

        merged_config = load_merged_config(service_name="voice", silent=True)
        _voice_settings = VoiceServiceSettings(**merged_config)
    return _voice_settings


def reset_voice_settings() -> None:
    global _voice_settings
    _voice_settings = None
