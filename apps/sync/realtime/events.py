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
from apps.sync.models.meetings import CallMeetingRead, CallRecordingRead
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
    "call.recording.started",
    "call.recording.stopped",
    "call.recording.failed",
    "call.transcript.ready",
    "call.transcript.failed",
    "call.summary.ready",
    "call.summary.failed",
    "call.export.crm.done",
    "call.export.crm.failed",
    "user.presence",
]


class RealtimeEvent(BaseModel):
    type: EventType
    channel_id: str | None = Field(default=None, description="Канал события, если применимо.")
    payload: dict = Field(description="Сериализованный payload события.")


class MessageStatusChangedPayload(BaseModel):
    message_id: str
    status: MessageStatus


def event_space_created(space: SpaceRead) -> RealtimeEvent:
    return RealtimeEvent(type="space.created", channel_id=None, payload=space.model_dump(mode="json"))


def event_channel_created(channel: ChannelRead) -> RealtimeEvent:
    return RealtimeEvent(type="channel.created", channel_id=channel.id, payload=channel.model_dump(mode="json"))


def event_channel_member_added(channel_id: str, added_user_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="channel.member_added",
        channel_id=channel_id,
        payload={"channel_id": channel_id, "added_user_id": added_user_id},
    )


def event_channel_read_updated(
    channel_id: str,
    reader_user_id: str,
    read_at: datetime,
) -> RealtimeEvent:
    return RealtimeEvent(
        type="channel.read_updated",
        channel_id=channel_id,
        payload={
            "channel_id": channel_id,
            "reader_user_id": reader_user_id,
            "read_at": read_at.isoformat(),
        },
    )


def event_channel_typing(
    *,
    channel_id: str,
    thread_id: str | None,
    typing: bool,
    user: UserBrief,
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
    )


def event_thread_created(thread: ThreadRead) -> RealtimeEvent:
    return RealtimeEvent(type="thread.created", channel_id=thread.channel_id, payload=thread.model_dump(mode="json"))


def event_message_created(message: MessageRead) -> RealtimeEvent:
    return RealtimeEvent(type="message.created", channel_id=message.channel_id, payload=message.model_dump(mode="json"))


def event_message_status_changed(channel_id: str, payload: MessageStatusChangedPayload) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.status_changed",
        channel_id=channel_id,
        payload=payload.model_dump(mode="json"),
    )


def event_git_resource_upserted(ref: GitResourceRefRead) -> RealtimeEvent:
    return RealtimeEvent(type="git_resource.upserted", channel_id=None, payload=ref.model_dump(mode="json"))


def event_message_updated(message: MessageRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.updated",
        channel_id=message.channel_id,
        payload=message.model_dump(mode="json"),
    )


def event_message_deleted(channel_id: str, message_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.deleted",
        channel_id=channel_id,
        payload={"message_id": message_id, "channel_id": channel_id},
    )


def event_message_reaction_changed(
    channel_id: str,
    message_id: str,
    reactions: list,
) -> RealtimeEvent:
    return RealtimeEvent(
        type="message.reaction_changed",
        channel_id=channel_id,
        payload={"message_id": message_id, "channel_id": channel_id, "reactions": reactions},
    )


def event_channel_pins_changed(channel: ChannelRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="channel.pins_changed",
        channel_id=channel.id,
        payload=channel.model_dump(mode="json"),
    )


def event_call_incoming(call: CallRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.incoming",
        channel_id=call.channel_id,
        payload=call.model_dump(mode="json"),
    )


def event_call_signal(call_id: str, signal_type: SignalType, data: dict) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.signal",
        channel_id=None,
        payload={"call_id": call_id, "signal_type": signal_type, "data": data},
    )


def event_call_accepted(call_id: str, user_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.accepted",
        channel_id=None,
        payload={"call_id": call_id, "user_id": user_id},
    )


def event_call_declined(call_id: str, user_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.declined",
        channel_id=None,
        payload={"call_id": call_id, "user_id": user_id},
    )


def event_call_ended(call: CallRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.ended",
        channel_id=call.channel_id,
        payload=call.model_dump(mode="json"),
    )


def event_call_participant_joined(call_id: str, user_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.participant_joined",
        channel_id=None,
        payload={"call_id": call_id, "user_id": user_id},
    )


def event_call_participant_left(call_id: str, user_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.participant_left",
        channel_id=None,
        payload={"call_id": call_id, "user_id": user_id},
    )


def event_call_recording_started(recording: CallRecordingRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.recording.started",
        channel_id=recording.channel_id,
        payload=recording.model_dump(mode="json"),
    )


def event_call_recording_stopped(recording: CallRecordingRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.recording.stopped",
        channel_id=recording.channel_id,
        payload=recording.model_dump(mode="json"),
    )


def event_call_recording_failed(recording: CallRecordingRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.recording.failed",
        channel_id=recording.channel_id,
        payload=recording.model_dump(mode="json"),
    )


def event_call_transcript_ready(meeting: CallMeetingRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.transcript.ready",
        channel_id=meeting.channel_id,
        payload=meeting.model_dump(mode="json"),
    )


def event_call_transcript_failed(meeting: CallMeetingRead, error: str) -> RealtimeEvent:
    payload = meeting.model_dump(mode="json")
    payload["error"] = error
    return RealtimeEvent(
        type="call.transcript.failed",
        channel_id=meeting.channel_id,
        payload=payload,
    )


def event_call_summary_ready(meeting: CallMeetingRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.summary.ready",
        channel_id=meeting.channel_id,
        payload=meeting.model_dump(mode="json"),
    )


def event_call_summary_failed(meeting: CallMeetingRead, error: str) -> RealtimeEvent:
    payload = meeting.model_dump(mode="json")
    payload["error"] = error
    return RealtimeEvent(
        type="call.summary.failed",
        channel_id=meeting.channel_id,
        payload=payload,
    )


def event_call_export_crm_done(meeting: CallMeetingRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.export.crm.done",
        channel_id=meeting.channel_id,
        payload=meeting.model_dump(mode="json"),
    )


def event_call_export_crm_failed(meeting: CallMeetingRead) -> RealtimeEvent:
    return RealtimeEvent(
        type="call.export.crm.failed",
        channel_id=meeting.channel_id,
        payload=meeting.model_dump(mode="json"),
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
    )
