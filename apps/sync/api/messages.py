"""REST-зеркала команд messages. Тонкие обвязки над `op_messages_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.sync.dependencies import ContainerDep
from apps.sync.models.channels import ChannelRead
from apps.sync.models.common import PaginationResponse
from apps.sync.models.messages import MessageCreate, MessageEdit, MessageRead
from apps.sync.realtime.operations import (
    MessagesDeletePayload,
    MessagesEditPayload,
    MessagesForwardPayload,
    MessagesListPayload,
    MessagesListThreadPayload,
    MessagesMarkReadPayload,
    MessagesPinPayload,
    MessagesReactPayload,
    MessagesSendPayload,
    MessagesTranscribeAudioPayload,
    MessagesTranscribeCallPayload,
    MessagesTranscribeCallResult,
    MessagesTranscribeVideoPayload,
    op_messages_delete,
    op_messages_edit,
    op_messages_forward,
    op_messages_list,
    op_messages_list_thread,
    op_messages_mark_read,
    op_messages_pin,
    op_messages_react,
    op_messages_send,
    op_messages_transcribe_audio,
    op_messages_transcribe_call,
    op_messages_transcribe_video,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.websocket import WsCommandError

router = APIRouter()


@router.get("/{channel_id}/messages", response_model=PaginationResponse[MessageRead])
async def list_messages(
    channel_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: str | None = None,
    after: str | None = None,
) -> PaginationResponse[MessageRead]:
    user = require_context().user
    return await op_messages_list(
        MessagesListPayload(
            channel_id=channel_id,
            limit=limit,
            before=before,
            after=after,
        ),
        user=user,
        container=container,
    )


@router.get(
    "/{channel_id}/threads/{thread_id}/messages",
    response_model=OffsetPage[MessageRead],
)
async def list_thread_messages(
    channel_id: str,
    thread_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[MessageRead]:
    """REST-зеркало `sync/messages/list_thread_requested`."""
    user = require_context().user
    return await op_messages_list_thread(
        MessagesListThreadPayload(
            channel_id=channel_id,
            thread_id=thread_id,
            limit=limit,
            offset=offset,
        ),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/messages", status_code=201, response_model=MessageRead)
async def send_message(
    container: ContainerDep, channel_id: str, body: MessageCreate
) -> MessageRead:
    user = require_context().user
    return await op_messages_send(
        MessagesSendPayload(channel_id=channel_id, body=body),
        user=user,
        container=container,
    )


@router.patch("/{channel_id}/messages/{message_id}", response_model=MessageRead)
async def edit_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
    body: MessageEdit,
) -> MessageRead:
    user = require_context().user
    return await op_messages_edit(
        MessagesEditPayload(channel_id=channel_id, message_id=message_id, body=body),
        user=user,
        container=container,
    )


@router.delete("/{channel_id}/messages/{message_id}", response_model=MessagesDeletePayload)
async def delete_message(
    container: ContainerDep, channel_id: str, message_id: str
) -> MessagesDeletePayload:
    user = require_context().user
    return await op_messages_delete(
        MessagesDeletePayload(channel_id=channel_id, message_id=message_id),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/messages/{message_id}/forward", status_code=201, response_model=MessageRead)
async def forward_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
    body: MessagesForwardPayload,
) -> MessageRead:
    if body.from_channel_id != channel_id or body.message_id != message_id:
        raise WsCommandError("ws_invalid_payload", "channel_id or message_id mismatch")
    user = require_context().user
    return await op_messages_forward(body, user=user, container=container)


@router.post("/{channel_id}/messages/{message_id}/react", response_model=MessageRead)
async def react_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
    body: MessagesReactPayload,
) -> MessageRead:
    if body.channel_id != channel_id or body.message_id != message_id:
        raise WsCommandError("ws_invalid_payload", "channel_id or message_id mismatch")
    user = require_context().user
    return await op_messages_react(body, user=user, container=container)


@router.post("/{channel_id}/messages/{message_id}/read", status_code=204)
async def mark_message_read(
    container: ContainerDep, channel_id: str, message_id: str
) -> None:
    """REST-зеркало команды `sync/messages/mark_read_requested`.

    Помечает конкретное сообщение как прочитанное и публикует
    `sync/message/status_changed` получателям канала. Не влияет на
    `sync_channel_members.last_read_at` — для обнуления unread-счётчика
    используется `POST /channels/{channel_id}/read` (op_channels_mark_read).
    """
    user = require_context().user
    await op_messages_mark_read(
        MessagesMarkReadPayload(channel_id=channel_id, message_id=message_id),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/pins", response_model=ChannelRead)
async def pin_message(
    container: ContainerDep, channel_id: str, body: MessagesPinPayload
) -> ChannelRead:
    if body.channel_id != channel_id:
        raise WsCommandError("ws_invalid_payload", "channel_id mismatch")
    user = require_context().user
    return await op_messages_pin(body, user=user, container=container)


@router.post("/{channel_id}/messages/{message_id}/transcribe", response_model=MessageRead)
async def transcribe_audio_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
) -> MessageRead:
    user = require_context().user
    return await op_messages_transcribe_audio(
        MessagesTranscribeAudioPayload(channel_id=channel_id, message_id=message_id),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/messages/{message_id}/transcribe-video", response_model=MessageRead)
async def transcribe_video_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
) -> MessageRead:
    user = require_context().user
    return await op_messages_transcribe_video(
        MessagesTranscribeVideoPayload(channel_id=channel_id, message_id=message_id),
        user=user,
        container=container,
    )


@router.post(
    "/{channel_id}/calls/{call_id}/transcribe",
    status_code=202,
    response_model=MessagesTranscribeCallResult,
)
async def transcribe_call_session(
    container: ContainerDep,
    channel_id: str,
    call_id: str,
) -> MessagesTranscribeCallResult:
    user = require_context().user
    return await op_messages_transcribe_call(
        MessagesTranscribeCallPayload(channel_id=channel_id, call_id=call_id),
        user=user,
        container=container,
    )
