"""События realtime слоя Sync (server -> client)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from apps.sync.models.calls import CallRead
from apps.sync.models.channels import ChannelRead
from apps.sync.models.common import UserBrief
from apps.sync.models.git import GitResourceRefRead
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.models.messages import MessageRead, MessageStatus, ReactionEntry
from apps.sync.models.threads import ThreadRead
from core.calls.models import SignalType
from core.types import JsonArray, JsonObject, parse_json_object

EventType = Literal[
    "sync/channel/created",
    "sync/channel/member_added",
    "sync/channel/read_updated",
    "sync/channel/typing",
    "sync/thread/created",
    "sync/message/created",
    "sync/message/status_changed",
    "sync/message/updated",
    "sync/message/deleted",
    "sync/message/reaction_changed",
    "sync/channel/pins_changed",
    "sync/git_resource/upserted",
    "sync/call/incoming",
    "sync/call/signaled",
    "sync/call/accepted",
    "sync/call/declined",
    "sync/call/ended",
    "sync/call/participant_joined",
    "sync/call/participant_left",
    "sync/call/admin_changed",
    "sync/call/recording_started",
    "sync/call/recording_stopped",
    "sync/call/recording_failed",
    "sync/presence/changed",
]


class RealtimeEvent(BaseModel):
    """Доменное событие Sync для рассылки через `platform:ui_events`.

    `channel_id` в payload остаётся (где нужно) — для фильтрации на клиенте.
    `company_id` / `recipient_user_ids` — адресация для `publish_realtime_events`,
    в проводной фрейм не уходят (определяют выбор `publish_ui_event_to_user`
    vs `publish_ui_event_to_company`).
    """

    type: EventType
    channel_id: str | None = Field(default=None, description="Канал события, если применимо.")
    payload: JsonObject = Field(description="Сериализованный payload события.")
    company_id: str = Field(description="Компания-получатель (изоляция между тенантами).")
    recipient_user_ids: list[str] | None = Field(
        default=None,
        description="None — broadcast компании; иначе адресная отправка перечисленным user_id.",
    )


class MessageStatusChangedPayload(BaseModel):
    message_id: str
    status: MessageStatus


def event_channel_created(
    channel: ChannelRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="sync/channel/created",
        channel_id=channel.channel_id,
        payload=parse_json_object(channel.model_dump_json(), "ChannelRead"),
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
        type="sync/channel/member_added",
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
        type="sync/channel/read_updated",
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
        type="sync/channel/typing",
        channel_id=channel_id,
        payload={
            "channel_id": channel_id,
            "thread_id": thread_id,
            "typing": typing,
            "user": parse_json_object(user.model_dump_json(), "UserBrief"),
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
        type="sync/thread/created",
        channel_id=thread.channel_id,
        payload=parse_json_object(thread.model_dump_json(), "ThreadRead"),
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
        type="sync/message/created",
        channel_id=message.channel_id,
        payload=parse_json_object(message.model_dump_json(), "MessageRead"),
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
        type="sync/message/status_changed",
        channel_id=channel_id,
        payload=parse_json_object(payload.model_dump_json(), "MessageStatusChangedPayload"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_git_resource_upserted(ref: GitResourceRefRead, *, company_id: str) -> RealtimeEvent:
    return RealtimeEvent(
        type="sync/git_resource/upserted",
        channel_id=None,
        payload=parse_json_object(ref.model_dump_json(), "GitResourceRefRead"),
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
        type="sync/message/updated",
        channel_id=message.channel_id,
        payload=parse_json_object(message.model_dump_json(), "MessageRead"),
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
        type="sync/message/deleted",
        channel_id=channel_id,
        payload={"message_id": message_id, "channel_id": channel_id},
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_message_reaction_changed(
    channel_id: str,
    message_id: str,
    reactions: list[ReactionEntry],
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    reaction_payload: JsonArray = [
        parse_json_object(reaction.model_dump_json(), "ReactionEntry")
        for reaction in reactions
    ]
    return RealtimeEvent(
        type="sync/message/reaction_changed",
        channel_id=channel_id,
        payload={
            "message_id": message_id,
            "channel_id": channel_id,
            "reactions": reaction_payload,
        },
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
        type="sync/channel/pins_changed",
        channel_id=channel.channel_id,
        payload=parse_json_object(channel.model_dump_json(), "ChannelRead"),
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
        type="sync/call/incoming",
        channel_id=call.channel_id,
        payload=parse_json_object(call.model_dump_json(), "CallRead"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_signal(
    call_id: str,
    signal_type: SignalType,
    data: JsonObject,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> RealtimeEvent:
    return RealtimeEvent(
        type="sync/call/signaled",
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
        type="sync/call/accepted",
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
        type="sync/call/declined",
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
        type="sync/call/ended",
        channel_id=call.channel_id,
        payload=parse_json_object(call.model_dump_json(), "CallRead"),
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
        type="sync/call/participant_joined",
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
        type="sync/call/participant_left",
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
        type="sync/call/admin_changed",
        channel_id=call.channel_id,
        payload=parse_json_object(call.model_dump_json(), "CallRead"),
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
        type="sync/call/recording_started",
        channel_id=recording.channel_id,
        payload=parse_json_object(recording.model_dump_json(), "CallRecordingRead"),
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
        type="sync/call/recording_stopped",
        channel_id=recording.channel_id,
        payload=parse_json_object(recording.model_dump_json(), "CallRecordingRead"),
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
        type="sync/call/recording_failed",
        channel_id=recording.channel_id,
        payload=parse_json_object(recording.model_dump_json(), "CallRecordingRead"),
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
        type="sync/presence/changed",
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
