"""Модели и JSON-контракты voice-сервиса."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, NotRequired, Required, TypeAlias, TypedDict

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from core.models import StrictBaseModel
from core.types import JsonObject, SpeechProvider, VadProvider


class VoiceProvidersHealth(BaseModel):
    """Snapshot deployment-default провайдеров речи."""

    status: Literal["ready"] = Field(description="Статус конфигурации voice-сервиса.")
    vad: Literal["ready"] = Field(description="Статус VAD-конфигурации.")
    stt_provider: SpeechProvider = Field(description="Deployment-default STT provider.")
    tts_provider: SpeechProvider = Field(description="Deployment-default TTS provider.")
    vad_provider: VadProvider = Field(description="Deployment-default VAD provider.")
    checked_at: datetime = Field(description="Время проверки health snapshot.")


class VoiceMediaUplinkConfig(TypedDict):
    encoding: Literal["pcm_s16le"]
    sample_rate: Literal[16000]
    channels: Literal[1]


class VoiceMediaConfigFrame(TypedDict):
    type: Literal["media_config"]
    mime: str
    sample_rate: int
    channels: int
    uplink: VoiceMediaUplinkConfig


class VoiceTranscriptFrame(TypedDict, total=False):
    type: Required[Literal["transcript"]]
    text: Required[str]
    final: Required[bool]
    language: NotRequired[str]
    interrupted: NotRequired[Literal[True]]


class VoiceVadFrame(TypedDict):
    type: Literal["vad"]
    state: Literal["started", "ended"]


class VoiceTtsStateFrame(TypedDict):
    type: Literal["tts_state"]
    state: Literal["playing", "stopped"]


class VoiceErrorFrame(TypedDict):
    type: Literal["error"]
    code: str
    detail: str


class VoicePingFrame(TypedDict):
    type: Literal["ping"]


class VoiceFinalizeDoneFrame(TypedDict):
    type: Literal["finalize_done"]


VoiceClientJsonFrame: TypeAlias = (
    VoiceMediaConfigFrame
    | VoiceTranscriptFrame
    | VoiceVadFrame
    | VoiceTtsStateFrame
    | VoiceErrorFrame
    | VoicePingFrame
    | VoiceFinalizeDoneFrame
)


class VoiceSpeakCommand(StrictBaseModel):
    type: Literal["speak"]
    text: str = Field(min_length=1)
    final: bool = False


class VoiceEndOfUtteranceCommand(StrictBaseModel):
    type: Literal["end_of_utterance"]


class VoiceStopPlaybackCommand(StrictBaseModel):
    type: Literal["stop_playback"]


class VoiceEndRecordingCommand(StrictBaseModel):
    type: Literal["end_recording"]


class VoiceConfigCommand(StrictBaseModel):
    type: Literal["config"]
    session: JsonObject | None = None


VoiceInboundCommand: TypeAlias = Annotated[
    VoiceSpeakCommand
    | VoiceEndOfUtteranceCommand
    | VoiceStopPlaybackCommand
    | VoiceEndRecordingCommand
    | VoiceConfigCommand,
    Field(discriminator="type"),
]

_VOICE_INBOUND_COMMAND_ADAPTER: TypeAdapter[VoiceInboundCommand] = TypeAdapter(
    VoiceInboundCommand
)


def parse_voice_inbound_command(payload: JsonObject) -> VoiceInboundCommand:
    """Проверить JSON-команду клиента на строгий voice WS contract."""
    try:
        return _VOICE_INBOUND_COMMAND_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise ValueError("Voice WS command violates contract") from exc
