"""
Профиль речи flow / ветки: STT, TTS, VAD без секретов провайдера.

Значения совместимы с подстановкой в ``SpeechOverride`` и query voice WS.
"""

from __future__ import annotations


from pydantic import Field

from core.clients.speech_override import SpeechProviderName, SpeechResponseFormat, VADProviderName
from core.models import StrictBaseModel


class FlowSpeechSttBlock(StrictBaseModel):
    provider: SpeechProviderName | None = Field(default=None)
    model: str | None = Field(default=None)
    language: str | None = Field(default=None)


class FlowSpeechTtsBlock(StrictBaseModel):
    provider: SpeechProviderName | None = Field(default=None)
    model: str | None = Field(default=None)
    voice: str | None = Field(default=None)
    language: str | None = Field(default=None)
    response_format: SpeechResponseFormat | None = Field(default=None)
    sample_rate: int | None = Field(default=None, gt=0)


class FlowSpeechVadBlock(StrictBaseModel):
    provider: VADProviderName | None = Field(default=None)
    sample_rate: int | None = Field(default=None, gt=0)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class FlowSpeechSettings(StrictBaseModel):
    stt: FlowSpeechSttBlock | None = Field(default=None)
    tts: FlowSpeechTtsBlock | None = Field(default=None)
    vad: FlowSpeechVadBlock | None = Field(default=None)


__all__ = [
    "FlowSpeechSettings",
    "FlowSpeechSttBlock",
    "FlowSpeechTtsBlock",
    "FlowSpeechVadBlock",
]
