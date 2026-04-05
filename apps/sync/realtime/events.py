"""События realtime слоя Sync (server -> client)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from apps.sync.models.calls import CallRead
from apps.sync.models.channels import ChannelRead
from apps.sync.models.common import UserBrief
from apps.sync.models.git import GitResourceRefRead
from apps.sync.models.messages import MessageRead, MessageStatus
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.models.spaces import SpaceRead
from apps.sync.models.threads import ThreadRead
from core.calls.models import SignalType


EventType = Literal[
    "space.created",
    "channel.created",
    "channel.member_added",
    "channel.read_updated",
    "channel.typing",
    "thread.created",
    "message.created",
    "message.status_changed",
    "message.updated",
    "message.deleted",
    "message.reaction_changed",
    "channel.pins_changed",
    "git_resource.upserted",
    "call.incoming",
    "call.signal",
    "call.accepted",
    "call.declined",
    "call.ended",
    "call.participant_joined",
    "call.participant_left",
    "call.admin.changed",
    "call.recording.started",
    "call.recording.stopped",
    "call.recording.failed",
    "user.presence",
]


class RealtimeEvent(BaseModel):
    type: EventType
    channel_id: str | None = Field(default=None, description="Канал события, если применимо.")
    payload: dict = Field(description="Сериализованный payload события.")
    company_id: str = Field(description="Компания-получатель (изоляция между тенантами).")
    recipient_user_ids: list[str] | None = Field(
        default=None,
        description="None — всем с активным /sync/ws в этой компании; иначе только перечисленным user_id.",
    )


class MessageStatusChangedPayload(BaseModel):
    message_id: str
    status: MessageStatus


def event_space_created(space: SpaceRead, *, company_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="space.created",
        channel_id=None,
        payload=space.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=None,
    )


def event_channel_created(
    channel: ChannelRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="channel.created",
        channel_id=channel.id,
        payload=channel.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_channel_member_added(
    channel_id: str,
    added_user_id: str,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="channel.member_added",
        channel_id=channel_id,
        payload={"channel_id": channel_id, "added_user_id": added_user_id},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_channel_read_updated(
    channel_id: str,
    reader_user_id: str,
    read_at: datetime,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="channel.read_updated",
        channel_id=channel_id,
        payload={
            "channel_id": channel_id,
            "reader_user_id": reader_user_id,
            "read_at": read_at.isoformat(),
        },
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_channel_typing(
    *,
    channel_id: str,
    thread_id: str | None,
    typing: bool,
    user: UserBrief,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="channel.typing",
        channel_id=channel_id,
        payload={
            "channel_id": channel_id,
            "thread_id": thread_id,
            "typing": typing,
            "user": user.model_dump(mode="json"),
        },
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_thread_created(
    thread: ThreadRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="thread.created",
        channel_id=thread.channel_id,
        payload=thread.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_message_created(
    message: MessageRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.created",
        channel_id=message.channel_id,
        payload=message.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_message_status_changed(
    channel_id: str,
    payload: MessageStatusChangedPayload,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.status_changed",
        channel_id=channel_id,
        payload=payload.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_git_resource_upserted(ref: GitResourceRefRead, *, company_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="git_resource.upserted",
        channel_id=None,
        payload=ref.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=None,
    )


def event_message_updated(
    message: MessageRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.updated",
        channel_id=message.channel_id,
        payload=message.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_message_deleted(
    channel_id: str,
    message_id: str,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.deleted",
        channel_id=channel_id,
        payload={"message_id": message_id, "channel_id": channel_id},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_message_reaction_changed(
    channel_id: str,
    message_id: str,
    reactions: list,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.reaction_changed",
        channel_id=channel_id,
        payload={"message_id": message_id, "channel_id": channel_id, "reactions": reactions},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_channel_pins_changed(
    channel: ChannelRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="channel.pins_changed",
        channel_id=channel.id,
        payload=channel.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_incoming(
    call: CallRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.incoming",
        channel_id=call.channel_id,
        payload=call.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_signal(
    call_id: str,
    signal_type: SignalType,
    data: dict,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.signal",
        channel_id=None,
        payload={"call_id": call_id, "signal_type": signal_type, "data": data},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_accepted(
    call_id: str,
    user_id: str,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.accepted",
        channel_id=None,
        payload={"call_id": call_id, "user_id": user_id},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_declined(
    call_id: str,
    user_id: str,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.declined",
        channel_id=None,
        payload={"call_id": call_id, "user_id": user_id},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_ended(
    call: CallRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.ended",
        channel_id=call.channel_id,
        payload=call.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_participant_joined(
    call_id: str,
    user_id: str,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.participant_joined",
        channel_id=None,
        payload={"call_id": call_id, "user_id": user_id},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_participant_left(
    call_id: str,
    user_id: str,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.participant_left",
        channel_id=None,
        payload={"call_id": call_id, "user_id": user_id},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_admin_changed(
    call: CallRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.admin.changed",
        channel_id=call.channel_id,
        payload=call.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_recording_started(
    recording: CallRecordingRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.recording.started",
        channel_id=recording.channel_id,
        payload=recording.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_recording_stopped(
    recording: CallRecordingRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.recording.stopped",
        channel_id=recording.channel_id,
        payload=recording.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_recording_failed(
    recording: CallRecordingRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.recording.failed",
        channel_id=recording.channel_id,
        payload=recording.model_dump(mode="json"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_user_presence(
    *,
    company_id: str,
    user_id: str,
    online: bool,
    last_seen_at: str | None,
) -> RealtimeEvent:
    return RealtimeEvent(
        type="user.presence",
        channel_id=None,
        payload={
            "company_id": company_id,
            "user_id": user_id,
            "online": online,
            "last_seen_at": last_seen_at,
        },
        company_id=company_id,
        recipient_user_ids=None,
    )
