"""Команды realtime слоя Sync (совместимы с REST DTO).

CommandEnvelope — единая внутренняя оболочка команды для бизнес-логики
`apps.sync.realtime.handlers.execute_command`. Тип внутри использует
короткие имена (`spaces.create`, `messages.send`, ...). Маппинг
каноничных WS-имён (`sync/<entity>/<verb>_requested`) в эти короткие типы
живёт в `apps/sync/realtime/command_router.py`.

Сама доставка фреймов идёт через `core.websocket.command_router`
(см. `architecture.mdc`, раздел «REST-зеркало команд»).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from apps.sync.models.calls import CallType
from apps.sync.models.channels import ChannelCreate, ChannelUpdate
from apps.sync.models.git import GitResourceRefCreate
from apps.sync.models.messages import MessageCreate, MessageEdit
from apps.sync.models.spaces import SpaceCreate, SpaceUpdate
from apps.sync.models.threads import ThreadCreate
from core.calls.models import SignalType


CommandType = Literal[
    "spaces.create",
    "spaces.update",
    "channels.create",
    "channels.update",
    "channels.mark_read",
    "channels.typing",
    "threads.create",
    "messages.send",
    "messages.mark_read",
    "messages.edit",
    "messages.delete",
    "messages.forward",
    "messages.react",
    "messages.pin",
    "messages.transcribe_audio",
    "messages.transcribe_video",
    "messages.transcribe_call",
    "git.resources.upsert",
    "call.invite",
    "call.signal",
    "call.accept",
    "call.decline",
    "call.hangup",
    "call.recording.start",
    "call.recording.stop",
    "call.admin.transfer",
]


class CommandEnvelope(BaseModel):
    """Единая оболочка команды.

    `id` приходит от клиента или генерируется WS-роутером.
    `company_id` проставляется из контекста для изоляции в воркере.
    """

    id: str = Field(description="UUID команды (client-generated или server-issued).")
    actor_user_id: str = Field(description="Пользователь, от имени которого выполняется команда.")
    company_id: str = Field(description="Компания для изоляции данных.")
    type: CommandType = Field(description="Тип команды.")
    payload: dict = Field(description="Payload команды (совместим с REST DTO).")


class SpacesCreatePayload(BaseModel):
    body: SpaceCreate


class SpacesUpdatePayload(BaseModel):
    space_id: str
    body: SpaceUpdate


class ChannelsCreatePayload(BaseModel):
    body: ChannelCreate


class ChannelsUpdatePayload(BaseModel):
    channel_id: str
    body: ChannelUpdate


class ChannelsMarkReadPayload(BaseModel):
    channel_id: str


class ChannelsTypingPayload(BaseModel):
    channel_id: str
    typing: bool
    thread_id: str | None = None


class ThreadsCreatePayload(BaseModel):
    body: ThreadCreate


class MessagesSendPayload(BaseModel):
    channel_id: str
    body: MessageCreate


class MessagesMarkReadPayload(BaseModel):
    channel_id: str
    message_id: str


class GitResourcesUpsertPayload(BaseModel):
    body: GitResourceRefCreate


class MessagesEditPayload(BaseModel):
    channel_id: str
    message_id: str
    body: MessageEdit


class MessagesDeletePayload(BaseModel):
    channel_id: str
    message_id: str


class MessagesForwardPayload(BaseModel):
    from_channel_id: str
    message_id: str
    to_channel_id: str
    thread_id: str | None = None


class MessagesReactPayload(BaseModel):
    channel_id: str
    message_id: str
    emoji: str | None = None


class MessagesPinPayload(BaseModel):
    channel_id: str
    message_id: str
    action: Literal["add", "remove"]


class MessagesTranscribeAudioPayload(BaseModel):
    channel_id: str
    message_id: str


class MessagesTranscribeVideoPayload(BaseModel):
    channel_id: str
    message_id: str


class MessagesTranscribeCallPayload(BaseModel):
    channel_id: str
    call_id: str


class CallInvitePayload(BaseModel):
    channel_id: str
    call_type: CallType = "video"

    @model_validator(mode="before")
    @classmethod
    def _legacy_audio_to_video(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("call_type") == "audio":
            return {**data, "call_type": "video"}
        return data


class CallSignalPayload(BaseModel):
    call_id: str
    target_user_id: str
    signal_type: SignalType
    data: dict


class CallAcceptPayload(BaseModel):
    call_id: str


class CallDeclinePayload(BaseModel):
    call_id: str


class CallHangupPayload(BaseModel):
    call_id: str


class CallRecordingStartPayload(BaseModel):
    call_id: str


class CallRecordingStopPayload(BaseModel):
    call_id: str


class CallTransferAdminPayload(BaseModel):
    call_id: str
    target_user_id: str
