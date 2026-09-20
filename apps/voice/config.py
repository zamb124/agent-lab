"""Конфигурация voice сервиса.

`VoiceServiceSettings` наследует `BaseSettings` — отсюда же приходит
`settings.voice: SpeechProvidersConfig` (deployment-default для STT/TTS/VAD).
В этом классе остаются только voice-специфичные блоки `barge_in` и
`queue` для real-time WS-сессии.
"""

from __future__ import annotations

from pydantic import Field

from core.config import BaseSettings
from core.config.models import (
    VoiceBargeInSettings,
    VoiceQueueSettings,
)
from core.config.service_settings import ServiceSettingsCache


class VoiceServiceSettings(BaseSettings):
    """Настройки voice сервиса (real-time WS-сессии)."""

    barge_in: VoiceBargeInSettings = Field(default_factory=VoiceBargeInSettings)
    queue: VoiceQueueSettings = Field(default_factory=VoiceQueueSettings)


_settings_cache = ServiceSettingsCache("voice", VoiceServiceSettings)
get_voice_settings = _settings_cache.get
reset_voice_settings = _settings_cache.reset
