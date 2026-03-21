"""Команды realtime слоя Sync (совместимы с REST DTO)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from apps.sync.models.channels import ChannelCreate, ChannelRead
from apps.sync.models.git import GitResourceRefCreate, GitResourceRefRead
from apps.sync.models.messages import MessageCreate, MessageEdit, MessageRead
from apps.sync.models.spaces import SpaceCreate, SpaceRead
from apps.sync.models.threads import ThreadCreate, ThreadRead


CommandType = Literal[
    "spaces.create",
    "channels.create",
    "threads.create",
    "messages.send",
    "messages.mark_read",
    "messages.edit",
    "messages.delete",
    "messages.forward",
    "messages.react",
    "messages.pin",
    "git.resources.upsert",
]


class CommandEnvelope(BaseModel):
    """Единая оболочка команды.

    `id` приходит от клиента (uuid). Сервер не генерирует id за клиента.
    `company_id` проставляется из контекста для изоляции в воркере.
    """

    id: str = Field(description="UUID команды (client-generated).")
    actor_user_id: str = Field(description="Пользователь, от имени которого выполняется команда.")
    company_id: str = Field(description="Компания для изоляции данных.")
    type: CommandType = Field(description="Тип команды.")
    payload: dict = Field(description="Payload команды (совместим с REST DTO).")


class WsCommandFrame(BaseModel):
    """Команда, пришедшая по WebSocket."""

    id: str = Field(description="UUID команды (client-generated).")
    type: CommandType = Field(description="Тип команды.")
    payload: dict = Field(description="Payload команды.")


class WsResultFrame(BaseModel):
    """Результат команды по WebSocket."""

    id: str
    ok: bool
    result: SpaceRead | ChannelRead | ThreadRead | MessageRead | GitResourceRefRead | None = None
    error_code: str | None = None
    error_detail: str | None = None


class SpacesCreatePayload(BaseModel):
    body: SpaceCreate


class ChannelsCreatePayload(BaseModel):
    body: ChannelCreate


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
