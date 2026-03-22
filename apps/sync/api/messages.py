"""API роутер для сообщений (Messages)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.sync.container import get_sync_container
from apps.sync.db.models import SyncMessage
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.common import PaginationRequest, UserBrief
from apps.sync.models.messages import MessageContentModel, MessageCreate, MessageEdit, MessageRead
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import handle_command
from core.context import get_context
from core.models.identity_models import User

router = APIRouter()


class MessageForwardBody(BaseModel):
    to_channel_id: str = Field(description="Целевой канал.")
    thread_id: str | None = Field(default=None, description="Опционально тред в целевом канале.")


class MessageReactBody(BaseModel):
    emoji: str | None = Field(default=None, description="Эмодзи или null чтобы снять.")


class MessagePinBody(BaseModel):
    message_id: str = Field(description="Сообщение для закрепа.")
    action: Literal["add", "remove"] = Field(description="Добавить или снять закреп.")


async def _message_read_from_entity(
    container,
    m: SyncMessage,
    users_by_id: dict[str, User],
) -> MessageRead:
    content_rows = await container.message_repository.list_contents(m.message_id)
    contents: list[MessageContentModel] = []
    for row in content_rows:
        contents.append(
            MessageContentModel.model_validate(
                {"type": row.type, "data": row.data, "order": row.order}
            )
        )
    u = users_by_id.get(m.sender_user_id)
    if u is None:
        sender = UserBrief(user_id=m.sender_user_id, display_name=m.sender_user_id, avatar_url=None)
    else:
        sender = UserBrief(user_id=m.sender_user_id, display_name=u.name, avatar_url=u.avatar_url)

    return message_read_from_entity(m=m, contents=contents, sender=sender)


@router.get("/{channel_id}/messages")
async def list_messages(
    channel_id: str,
    pagination: PaginationRequest = Depends(),
) -> list[MessageRead]:
    """Сообщения канала: полная модель с отправителем и контентом (как в MessageRead / WS)."""
    context = get_context()
    container = get_sync_container()
    rows = await container.message_repository.list_by_channel(
        channel_id,
        limit=pagination.limit,
        company_id=context.active_company.company_id,
    )
    if not rows:
        return []

    user_ids = list({m.sender_user_id for m in rows})
    users_by_id = await container.user_repository.get_many(user_ids)

    chronological = list(reversed(rows))
    return [await _message_read_from_entity(container, m, users_by_id) for m in chronological]


@router.post("/{channel_id}/messages", status_code=201)
async def send_message(channel_id: str, body: MessageCreate) -> dict:
    """Отправка сообщения через TaskIQ."""
    context = get_context()
    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="messages.send",
        payload={"channel_id": channel_id, "body": body.model_dump()},
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(timeout=300.0)
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    return res.return_value["result"]


async def _run_cmd(cmd_type: str, payload: dict) -> dict:
    context = get_context()
    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type=cmd_type,
        payload=payload,
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(timeout=300.0)
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    return res.return_value["result"]


@router.patch("/{channel_id}/messages/{message_id}")
async def edit_message(channel_id: str, message_id: str, body: MessageEdit) -> dict:
    return await _run_cmd(
        "messages.edit",
        {"channel_id": channel_id, "message_id": message_id, "body": body.model_dump(mode="json")},
    )


@router.delete("/{channel_id}/messages/{message_id}")
async def delete_message(channel_id: str, message_id: str) -> dict:
    return await _run_cmd(
        "messages.delete",
        {"channel_id": channel_id, "message_id": message_id},
    )


@router.post("/{channel_id}/messages/{message_id}/forward", status_code=201)
async def forward_message(channel_id: str, message_id: str, body: MessageForwardBody) -> dict:
    return await _run_cmd(
        "messages.forward",
        {
            "from_channel_id": channel_id,
            "message_id": message_id,
            "to_channel_id": body.to_channel_id,
            "thread_id": body.thread_id,
        },
    )


@router.post("/{channel_id}/messages/{message_id}/react")
async def react_message(channel_id: str, message_id: str, body: MessageReactBody) -> dict:
    return await _run_cmd(
        "messages.react",
        {"channel_id": channel_id, "message_id": message_id, "emoji": body.emoji},
    )


@router.post("/{channel_id}/pins")
async def pin_message(channel_id: str, body: MessagePinBody) -> dict:
    return await _run_cmd(
        "messages.pin",
        {"channel_id": channel_id, "message_id": body.message_id, "action": body.action},
    )
