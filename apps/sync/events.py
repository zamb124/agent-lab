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
from core.events import register_platform_event
from core.events.contract import EventDelivery, PlatformEvent
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
]


def sync_platform_event(
    *,
    type: EventType,
    company_id: str,
    payload: JsonObject,
    recipient_user_ids: list[str] | None,
    channel_id: str | None = None,
) -> PlatformEvent:
    body = dict(payload)
    if channel_id is not None and "channel_id" not in body:
        body["channel_id"] = channel_id
    if recipient_user_ids is None:
        delivery = EventDelivery(company_id=company_id)
    else:
        delivery = EventDelivery(user_ids=list(recipient_user_ids))
    return PlatformEvent(
        type=type,
        company_id=company_id,
        payload=body,
        delivery=delivery,
    )


class MessageStatusChangedPayload(BaseModel):
    message_id: str
    status: MessageStatus


class MessageCreatedEventPayload(MessageRead):
    """Payload `sync/message/created`: сообщение + контекст канала.

    `channel_type` и `recipient_user_ids` нужны durable-потребителям шины
    (триггеры flows, routing flow-сотрудников: DM или @mention).
    """

    channel_type: str
    recipient_user_ids: list[str]
    local_id: str | None = None


class MessageDeletedEventPayload(BaseModel):
    """Payload `sync/message/deleted`."""

    message_id: str
    channel_id: str


def event_channel_created(
    channel: ChannelRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
    channel_type: str,
    local_id: str | None = None,
) -> PlatformEvent:
    enriched = MessageCreatedEventPayload.model_validate(
        {
            **message.model_dump(),
            "channel_type": channel_type,
            "recipient_user_ids": recipient_user_ids,
            "local_id": local_id,
        }
    )
    return sync_platform_event(
        type="sync/message/created",
        channel_id=message.channel_id,
        payload=parse_json_object(enriched.model_dump_json(), "MessageCreatedEventPayload"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_message_status_changed(
    channel_id: str,
    payload: MessageStatusChangedPayload,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> PlatformEvent:
    return sync_platform_event(
        type="sync/message/status_changed",
        channel_id=channel_id,
        payload=parse_json_object(payload.model_dump_json(), "MessageStatusChangedPayload"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_git_resource_upserted(ref: GitResourceRefRead, *, company_id: str) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    reaction_payload: JsonArray = [
        parse_json_object(reaction.model_dump_json(), "ReactionEntry")
        for reaction in reactions
    ]
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
        type="sync/channel/pins_changed",
        channel_id=channel.channel_id,
        payload=parse_json_object(channel.model_dump_json(), "ChannelRead"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


class CallIncomingEventPayload(CallRead):
    initiator_user_id: str
    caller_display_name: str
    incoming_channel_kind: str
    channel_display_name: str | None = None


def event_call_incoming(
    call: CallRead,
    *,
    company_id: str,
    recipient_user_ids: list[str],
    initiator_user_id: str,
    caller_display_name: str,
    incoming_channel_kind: str,
    channel_display_name: str | None = None,
) -> PlatformEvent:
    payload = CallIncomingEventPayload.model_validate(
        {
            **call.model_dump(),
            "initiator_user_id": initiator_user_id,
            "caller_display_name": caller_display_name,
            "incoming_channel_kind": incoming_channel_kind,
            "channel_display_name": channel_display_name,
        }
    )
    return sync_platform_event(
        type="sync/call/incoming",
        channel_id=call.channel_id,
        payload=parse_json_object(payload.model_dump_json(), "CallIncomingEventPayload"),
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
    target_user_id: str,
    sender_user_id: str,
) -> PlatformEvent:
    return sync_platform_event(
        type="sync/call/signaled",
        channel_id=None,
        payload={
            "call_id": call_id,
            "signal_type": signal_type,
            "data": data,
            "target_user_id": target_user_id,
            "sender_user_id": sender_user_id,
        },
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


def event_call_accepted(
    call_id: str,
    user_id: str,
    *,
    company_id: str,
    recipient_user_ids: list[str],
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
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
) -> PlatformEvent:
    return sync_platform_event(
        type="sync/call/recording_failed",
        channel_id=recording.channel_id,
        payload=parse_json_object(recording.model_dump_json(), "CallRecordingRead"),
        company_id=company_id,
        recipient_user_ids=recipient_user_ids,
    )


class SyncChannelMemberAddedPayload(BaseModel):
    channel_id: str
    added_user_id: str


class SyncChannelReadUpdatedPayload(BaseModel):
    channel_id: str
    reader_user_id: str
    read_at: str


class SyncChannelTypingPayload(BaseModel):
    channel_id: str
    thread_id: str | None = None
    typing: bool
    user: JsonObject


class SyncMessageReactionChangedPayload(BaseModel):
    message_id: str
    channel_id: str
    reactions: list[ReactionEntry] = Field(default_factory=list)


class SyncCallSignaledPayload(BaseModel):
    call_id: str
    signal_type: SignalType
    data: JsonObject = Field(default_factory=dict)
    target_user_id: str
    sender_user_id: str


class SyncCallUserPayload(BaseModel):
    call_id: str
    user_id: str


register_platform_event(
    "sync/message/created",
    MessageCreatedEventPayload,
    description="Новое сообщение в канале Sync (payload: сообщение + channel_type + получатели).",
)
register_platform_event(
    "sync/message/updated",
    MessageRead,
    description="Сообщение Sync изменено (edit/transcription/react side effects).",
)
register_platform_event(
    "sync/message/deleted",
    MessageDeletedEventPayload,
    description="Сообщение Sync удалено.",
)
register_platform_event(
    "sync/message/status_changed",
    MessageStatusChangedPayload,
    description="Статус доставки/прочтения сообщения Sync изменён.",
)
register_platform_event(
    "sync/message/reaction_changed",
    SyncMessageReactionChangedPayload,
    description="Реакции на сообщение Sync изменены.",
)
register_platform_event(
    "sync/channel/created",
    ChannelRead,
    description="Создан канал Sync (direct/group/topic/calendar_meeting).",
)
register_platform_event(
    "sync/channel/member_added",
    SyncChannelMemberAddedPayload,
    description="В канал Sync добавлен участник.",
)
register_platform_event(
    "sync/channel/read_updated",
    SyncChannelReadUpdatedPayload,
    description="Обновлена метка прочтения канала Sync.",
)
register_platform_event(
    "sync/channel/typing",
    SyncChannelTypingPayload,
    description="Индикатор набора текста в канале Sync.",
)
register_platform_event(
    "sync/channel/pins_changed",
    ChannelRead,
    description="Изменён список закреплённых сообщений канала Sync.",
)
register_platform_event(
    "sync/thread/created",
    ThreadRead,
    description="Создан тред в канале Sync.",
)
register_platform_event(
    "sync/git_resource/upserted",
    GitResourceRefRead,
    description="Git-ресурс Sync создан или обновлён.",
)
register_platform_event(
    "sync/call/incoming",
    CallIncomingEventPayload,
    description="Входящий звонок Sync.",
)
register_platform_event(
    "sync/call/signaled",
    SyncCallSignaledPayload,
    description="Сигнал WebRTC/LiveKit в звонке Sync.",
)
register_platform_event(
    "sync/call/accepted",
    SyncCallUserPayload,
    description="Звонок Sync принят.",
)
register_platform_event(
    "sync/call/declined",
    SyncCallUserPayload,
    description="Звонок Sync отклонён.",
)
register_platform_event(
    "sync/call/ended",
    CallRead,
    description="Звонок Sync завершён (все участники вышли).",
)
register_platform_event(
    "sync/call/participant_joined",
    SyncCallUserPayload,
    description="Участник присоединился к звонку Sync.",
)
register_platform_event(
    "sync/call/participant_left",
    SyncCallUserPayload,
    description="Участник покинул звонок Sync.",
)
register_platform_event(
    "sync/call/admin_changed",
    CallRead,
    description="Изменён список админов звонка Sync.",
)
register_platform_event(
    "sync/call/recording_started",
    CallRecordingRead,
    description="Начата запись звонка Sync.",
)
register_platform_event(
    "sync/call/recording_stopped",
    CallRecordingRead,
    description="Запись звонка Sync остановлена.",
)
register_platform_event(
    "sync/call/recording_failed",
    CallRecordingRead,
    description="Ошибка записи звонка Sync.",
)
