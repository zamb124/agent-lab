"""Pydantic модели для WebRTC звонков."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

CallStatus = Literal["ringing", "active", "ended"]
CallType = Literal["video"]
CallMode = Literal["p2p", "sfu"]
ParticipantStatus = Literal["invited", "joined", "declined", "left"]


class CallParticipantRead(BaseModel):
    user_id: str
    status: ParticipantStatus
    joined_at: Optional[datetime] = None
    left_at: Optional[datetime] = None


class CallRead(BaseModel):
    call_id: str
    channel_id: str
    mode: CallMode
    call_type: CallType
    status: CallStatus
    livekit_room_name: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    created_by_user_id: str
    participants: list[CallParticipantRead] = []


class CallLinkCreate(BaseModel):
    channel_id: str
    call_type: CallType = "video"
    ttl_hours: int = Field(default=24, ge=1, le=168)
    call_id: Optional[str] = Field(
        default=None,
        description="Текущий звонок: та же LiveKit-комната, что у участников чата.",
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_audio_to_video(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("call_type") == "audio":
            return {**data, "call_type": "video"}
        return data


class CallLinkRead(BaseModel):
    link_token: str
    channel_id: str
    call_type: CallType
    expires_at: datetime
    join_url: str


class CallLinkInfo(BaseModel):
    """Публичная информация о ссылке (без auth)."""
    link_token: str
    channel_name: Optional[str]
    creator_display_name: str
    creator_avatar_url: Optional[str] = Field(
        default=None,
        description="URL аватара создателя ссылки (если задан в профиле).",
    )
    call_type: CallType
    expires_at: datetime


class GuestJoinRequest(BaseModel):
    guest_name: str = Field(min_length=1, max_length=64)


class JoinResponse(BaseModel):
    """Ответ при входе в звонок (registered или guest)."""
    call_id: str
    livekit_token: str
    livekit_url: str
    identity: str
    mode: CallMode
    participant_names: dict[str, str] = Field(
        default_factory=dict,
        description="LiveKit identity -> отображаемое имя (для гостя без карты участников компании).",
    )
