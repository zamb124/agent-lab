"""
Профиль речи flow / ветки: STT, TTS, VAD без секретов провайдера.

Значения совместимы с подстановкой в ``SpeechOverride`` и query voice WS.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from core.clients.speech_override import SpeechProviderName, SpeechResponseFormat, VADProviderName
from core.models import StrictBaseModel


class FlowSpeechSttBlock(StrictBaseModel):
    provider: Optional[SpeechProviderName] = Field(default=None)
    model: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)


class FlowSpeechTtsBlock(StrictBaseModel):
    provider: Optional[SpeechProviderName] = Field(default=None)
    model: Optional[str] = Field(default=None)
    voice: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)
    response_format: Optional[SpeechResponseFormat] = Field(default=None)
    sample_rate: Optional[int] = Field(default=None, gt=0)


class FlowSpeechVadBlock(StrictBaseModel):
    provider: Optional[VADProviderName] = Field(default=None)
    sample_rate: Optional[int] = Field(default=None, gt=0)
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class FlowSpeechSettings(StrictBaseModel):
    stt: Optional[FlowSpeechSttBlock] = Field(default=None)
    tts: Optional[FlowSpeechTtsBlock] = Field(default=None)
    vad: Optional[FlowSpeechVadBlock] = Field(default=None)


__all__ = [
    "FlowSpeechSettings",
    "FlowSpeechSttBlock",
    "FlowSpeechTtsBlock",
    "FlowSpeechVadBlock",
]
