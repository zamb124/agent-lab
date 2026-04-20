"""Pydantic-payload-модели звонков для `apps.sync.realtime.call_handlers`.

Все остальные payload-модели команд Sync живут в
`apps/sync/realtime/operations.py` рядом с `op_*` функциями. Здесь только
модели, которые исторически нужны `handle_call_invite/accept/decline/hangup`
для валидации `cmd.payload` (внутри shim-объекта `_CallCmdShim`).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from apps.sync.models.calls import CallType
from core.calls.models import SignalType


class CallInvitePayload(BaseModel):
    channel_id: str = Field(min_length=1)
    call_type: CallType = "video"

    @model_validator(mode="before")
    @classmethod
    def _legacy_audio_to_video(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("call_type") == "audio":
            return {**data, "call_type": "video"}
        return data


class CallSignalPayload(BaseModel):
    call_id: str = Field(min_length=1)
    target_user_id: str = Field(min_length=1)
    signal_type: SignalType
    data: dict[str, Any]


class CallAcceptPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallDeclinePayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallHangupPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallRecordingStartPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallRecordingStopPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallTransferAdminPayload(BaseModel):
    call_id: str = Field(min_length=1)
    target_user_id: str = Field(min_length=1)
