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
    channel_id: Optional[str] = Field(
        default=None,
        description="Канал существующего чата. Не указывать вместе с calendar_event_id.",
    )
    call_type: CallType = "video"
    ttl_hours: int = Field(default=24, ge=1, le=168)
    call_id: Optional[str] = Field(
        default=None,
        description="Текущий звонок: та же LiveKit-комната, что у участников чата.",
    )
    calendar_event_id: Optional[str] = Field(
        default=None,
        description="ID события platform calendar: создаётся канал calendar_meeting и ссылка.",
    )
    scheduled_title: Optional[str] = None
    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None
    calendar_member_user_ids: Optional[list[str]] = Field(
        default=None,
        description="Участники канала встречи (platform user_id), без создателя.",
    )
    reuse_channel_link: bool = Field(
        default=True,
        description="Для channel без calendar: вернуть существующую постоянную ссылку и продлить TTL.",
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_audio_to_video(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("call_type") == "audio":
            return {**data, "call_type": "video"}
        return data

    @model_validator(mode="after")
    def _calendar_or_channel(self) -> "CallLinkCreate":
        if self.calendar_event_id:
            if self.channel_id is not None:
                raise ValueError("При calendar_event_id не передавайте channel_id.")
            if self.scheduled_title is None or self.scheduled_title.strip() == "":
                raise ValueError("Для календарной ссылки нужен scheduled_title.")
            if self.scheduled_start_at is None or self.scheduled_end_at is None:
                raise ValueError("Нужны scheduled_start_at и scheduled_end_at.")
            if self.scheduled_start_at >= self.scheduled_end_at:
                raise ValueError("scheduled_start_at должен быть раньше scheduled_end_at.")
            if self.calendar_member_user_ids is None:
                raise ValueError("Передайте calendar_member_user_ids (список, может быть пустым).")
            if self.call_id is not None:
                raise ValueError("call_id несовместим с календарной ссылкой.")
        else:
            if self.channel_id is None or self.channel_id == "":
                raise ValueError("Укажите channel_id или блок календаря с calendar_event_id.")
        return self


class CallLinkRead(BaseModel):
    link_token: str
    channel_id: str
    call_type: CallType
    expires_at: datetime
    join_url: str
    title: Optional[str] = None
    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None
    calendar_event_id: Optional[str] = None


class CallLinkPatch(BaseModel):
    scheduled_title: Optional[str] = None
    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None
    calendar_member_user_ids: Optional[list[str]] = Field(
        default=None,
        description="Полная синхронизация участников канала встречи (кроме создателя ссылки).",
    )

    @model_validator(mode="after")
    def _has_update(self) -> "CallLinkPatch":
        has_schedule = (
            self.scheduled_title is not None
            or self.scheduled_start_at is not None
            or self.scheduled_end_at is not None
        )
        has_members = self.calendar_member_user_ids is not None
        if not has_schedule and not has_members:
            raise ValueError("Укажите хотя бы одно поле для обновления.")
        if (
            self.scheduled_start_at is not None
            and self.scheduled_end_at is not None
            and self.scheduled_start_at >= self.scheduled_end_at
        ):
            raise ValueError("scheduled_start_at должен быть раньше scheduled_end_at.")
        return self


class CallScheduledLinkRead(BaseModel):
    link_token: str
    channel_id: str
    title: Optional[str]
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    calendar_event_id: str
    join_url: str
    expires_at: datetime


class CallLinkInfo(BaseModel):
    """Публичная информация о ссылке (без auth)."""
    link_token: str
    company_id: str
    channel_id: str
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
    call_type: CallType
    livekit_token: str
    livekit_url: str
    identity: str
    meeting_admin_user_id: str
    mode: CallMode
    participant_names: dict[str, str] = Field(
        default_factory=dict,
        description="LiveKit identity -> отображаемое имя (для гостя без карты участников компании).",
    )
