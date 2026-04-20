"""REST-зеркала команд messages. Тонкие обвязки над `op_messages_*`."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from apps.sync.dependencies import ContainerDep
from apps.sync.models.common import PaginationResponse
from apps.sync.models.messages import MessageCreate, MessageEdit, MessageRead
from apps.sync.realtime.operations import (
    MessagesDeletePayload,
    MessagesEditPayload,
    MessagesForwardPayload,
    MessagesListPayload,
    MessagesMarkReadPayload,
    MessagesPinPayload,
    MessagesReactPayload,
    MessagesSendPayload,
    MessagesTranscribeAudioPayload,
    MessagesTranscribeCallPayload,
    MessagesTranscribeVideoPayload,
    op_messages_delete,
    op_messages_edit,
    op_messages_forward,
    op_messages_list,
    op_messages_mark_read,
    op_messages_pin,
    op_messages_react,
    op_messages_send,
    op_messages_transcribe_audio,
    op_messages_transcribe_call,
    op_messages_transcribe_video,
)
from core.context import get_context

router = APIRouter()
MESSAGES_DEFAULT_LIMIT = 20


class _MessagePaginationRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    before: str | None = Field(default=None)
    after: str | None = Field(default=None)


class MessageForwardBody(BaseModel):
    to_channel_id: str = Field(min_length=1)
    thread_id: str | None = Field(default=None)


class MessageReactBody(BaseModel):
    emoji: str | None = Field(default=None)


class MessagePinBody(BaseModel):
    message_id: str = Field(min_length=1)
    action: Literal["add", "remove"]


@router.get("/{channel_id}/messages", response_model=PaginationResponse[MessageRead])
async def list_messages(
    channel_id: str,
    request: Request,
    container: ContainerDep,
    pagination: _MessagePaginationRequest = Depends(),
) -> PaginationResponse[MessageRead]:
    user = get_context().user
    limit = pagination.limit
    if "limit" not in request.query_params:
        limit = MESSAGES_DEFAULT_LIMIT
    result = await op_messages_list(
        MessagesListPayload(
            channel_id=channel_id,
            limit=limit,
            before=pagination.before,
            after=pagination.after,
        ),
        user=user,
        container=container,
    )
    return PaginationResponse[MessageRead](
        items=result.items,
        next_cursor=result.next_cursor,
        prev_cursor=result.prev_cursor,
    )


@router.post("/{channel_id}/messages", status_code=201, response_model=MessageRead)
async def send_message(
    container: ContainerDep, channel_id: str, body: MessageCreate
) -> MessageRead:
    user = get_context().user
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
    user = get_context().user
    return await op_messages_edit(
        MessagesEditPayload(channel_id=channel_id, message_id=message_id, body=body),
        user=user,
        container=container,
    )


@router.delete("/{channel_id}/messages/{message_id}")
async def delete_message(
    container: ContainerDep, channel_id: str, message_id: str
) -> dict[str, str]:
    user = get_context().user
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
    body: MessageForwardBody,
) -> MessageRead:
    user = get_context().user
    return await op_messages_forward(
        MessagesForwardPayload(
            from_channel_id=channel_id,
            message_id=message_id,
            to_channel_id=body.to_channel_id,
            thread_id=body.thread_id,
        ),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/messages/{message_id}/react", response_model=MessageRead)
async def react_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
    body: MessageReactBody,
) -> MessageRead:
    user = get_context().user
    return await op_messages_react(
        MessagesReactPayload(
            channel_id=channel_id, message_id=message_id, emoji=body.emoji
        ),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/messages/{message_id}/read")
async def mark_message_read(
    container: ContainerDep, channel_id: str, message_id: str
) -> dict[str, str]:
    """REST-зеркало команды `sync/messages/mark_read_requested`.

    Помечает конкретное сообщение как прочитанное и публикует
    `sync/message/status_changed` получателям канала. Не влияет на
    `sync_channel_members.last_read_at` — для обнуления unread-счётчика
    используется `POST /channels/{channel_id}/read` (op_channels_mark_read).
    """
    user = get_context().user
    await op_messages_mark_read(
        MessagesMarkReadPayload(channel_id=channel_id, message_id=message_id),
        user=user,
        container=container,
    )
    return {"message_id": message_id}


@router.post("/{channel_id}/pins")
async def pin_message(
    container: ContainerDep, channel_id: str, body: MessagePinBody
) -> dict:
    user = get_context().user
    result = await op_messages_pin(
        MessagesPinPayload(
            channel_id=channel_id, message_id=body.message_id, action=body.action
        ),
        user=user,
        container=container,
    )
    return result.model_dump(mode="json")


@router.post("/{channel_id}/messages/{message_id}/transcribe", response_model=MessageRead)
async def transcribe_audio_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
) -> MessageRead:
    user = get_context().user
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
    user = get_context().user
    return await op_messages_transcribe_video(
        MessagesTranscribeVideoPayload(channel_id=channel_id, message_id=message_id),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/calls/{call_id}/transcribe", status_code=202)
async def transcribe_call_session(
    container: ContainerDep,
    channel_id: str,
    call_id: str,
) -> dict[str, str]:
    user = get_context().user
    result = await op_messages_transcribe_call(
        MessagesTranscribeCallPayload(channel_id=channel_id, call_id=call_id),
        user=user,
        container=container,
    )
    return {"status": result.status}
