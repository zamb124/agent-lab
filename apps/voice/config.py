"""Конфигурация voice сервиса."""

from __future__ import annotations

from typing import Optional

from core.config import BaseSettings
from core.config.models import (
    VoiceBargeInSettings,
    VoiceQueueSettings,
    VoiceSTTSettings,
    VoiceTTSSettings,
    VoiceVADSettings,
)
from pydantic import Field


class VoiceServiceSettings(BaseSettings):
    """Настройки voice сервиса."""

    stt: VoiceSTTSettings = Field(default_factory=VoiceSTTSettings)
    tts: VoiceTTSSettings = Field(default_factory=VoiceTTSSettings)
    vad: VoiceVADSettings = Field(default_factory=VoiceVADSettings)
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
