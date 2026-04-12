"""API роутер для сообщений (Messages)."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from apps.sync.dependencies import ContainerDep
from apps.sync.db.models import SyncMessage
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.common import PaginationResponse, UserBrief
from apps.sync.models.messages import MessageContentModel, MessageCreate, MessageEdit, MessageRead
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import handle_command
from core.config import get_settings
from core.context import get_context
from core.models.identity_models import User

router = APIRouter()
MESSAGES_DEFAULT_LIMIT = 20


class _MessagePaginationRequest(BaseModel):
    """Параметры двунаправленной курсорной пагинации чата."""

    limit: int = Field(default=50, ge=1, le=200)
    before: str | None = Field(default=None)
    after: str | None = Field(default=None)


def _encode_message_cursor(*, sent_at: datetime, message_id: str) -> str:
    payload = {"sent_at": sent_at.isoformat(), "message_id": message_id}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_message_cursor(cursor: str) -> tuple[datetime, str]:
    padded = cursor + ("=" * ((4 - len(cursor) % 4) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload = json.loads(raw)
    except Exception as error:
        raise HTTPException(status_code=400, detail="Некорректный формат cursor.") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Некорректный формат cursor payload.")
    sent_at_raw = payload.get("sent_at")
    message_id = payload.get("message_id")
    if not isinstance(sent_at_raw, str) or sent_at_raw == "":
        raise HTTPException(status_code=400, detail="cursor.sent_at обязателен.")
    if not isinstance(message_id, str) or message_id == "":
        raise HTTPException(status_code=400, detail="cursor.message_id обязателен.")
    try:
        sent_at = datetime.fromisoformat(sent_at_raw)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="cursor.sent_at должен быть ISO datetime.") from error
    return sent_at, message_id


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
    request: Request,
    container: ContainerDep,
    pagination: _MessagePaginationRequest = Depends(),
) -> PaginationResponse[MessageRead]:
    """Сообщения канала: полная модель с отправителем и контентом (как в MessageRead / WS)."""
    context = get_context()

    if pagination.before is not None and pagination.after is not None:
        raise HTTPException(status_code=400, detail="Нельзя одновременно передавать before и after.")

    limit = pagination.limit
    if "limit" not in request.query_params:
        limit = MESSAGES_DEFAULT_LIMIT

    before_sent_at: datetime | None = None
    before_message_id: str | None = None
    if pagination.before is not None:
        before_sent_at, before_message_id = _decode_message_cursor(pagination.before)

    after_sent_at: datetime | None = None
    after_message_id: str | None = None
    if pagination.after is not None:
        after_sent_at, after_message_id = _decode_message_cursor(pagination.after)

    window = await container.message_repository.list_by_channel_cursor(
        channel_id=channel_id,
        limit=limit,
        before_sent_at=before_sent_at,
        before_message_id=before_message_id,
        after_sent_at=after_sent_at,
        after_message_id=after_message_id,
        company_id=context.active_company.company_id,
    )
    rows = window.rows
    if not rows:
        return PaginationResponse[MessageRead](
            items=[],
            next_cursor=None,
            prev_cursor=None,
        )

    user_ids = list({m.sender_user_id for m in rows})
    users_by_id = await container.user_repository.get_many(user_ids)

    chronological = list(reversed(rows))
    items = [await _message_read_from_entity(container, m, users_by_id) for m in chronological]

    oldest = chronological[0]
    newest = chronological[-1]
    next_cursor = None
    if window.has_more_older:
        next_cursor = _encode_message_cursor(sent_at=oldest.sent_at, message_id=oldest.message_id)
    prev_cursor = None
    if window.has_more_newer:
        prev_cursor = _encode_message_cursor(sent_at=newest.sent_at, message_id=newest.message_id)

    return PaginationResponse[MessageRead](
        items=items,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
    )


@router.post("/{channel_id}/messages", status_code=201)
async def send_message(container: ContainerDep, channel_id: str, body: MessageCreate) -> dict:
    """Отправка сообщения через TaskIQ."""
    _ = container
    context = get_context()
    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="messages.send",
        payload={"channel_id": channel_id, "body": body.model_dump()},
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(
        timeout=get_settings().sync_taskiq_wait_result_timeout_seconds,
    )
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
    res = await task.wait_result(
        timeout=get_settings().sync_taskiq_wait_result_timeout_seconds,
    )
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    result = res.return_value["result"]
    if result is None:
        raise RuntimeError("Команда вернула пустой result.")
    return result


async def _run_cmd_allow_null_result(cmd_type: str, payload: dict) -> None:
    context = get_context()
    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type=cmd_type,
        payload=payload,
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(
        timeout=get_settings().sync_taskiq_wait_result_timeout_seconds,
    )
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")


@router.patch("/{channel_id}/messages/{message_id}")
async def edit_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
    body: MessageEdit,
) -> dict:
    _ = container
    return await _run_cmd(
        "messages.edit",
        {"channel_id": channel_id, "message_id": message_id, "body": body.model_dump(mode="json")},
    )


@router.delete("/{channel_id}/messages/{message_id}")
async def delete_message(container: ContainerDep, channel_id: str, message_id: str) -> dict:
    _ = container
    return await _run_cmd(
        "messages.delete",
        {"channel_id": channel_id, "message_id": message_id},
    )


@router.post("/{channel_id}/messages/{message_id}/forward", status_code=201)
async def forward_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
    body: MessageForwardBody,
) -> dict:
    _ = container
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
async def react_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
    body: MessageReactBody,
) -> dict:
    _ = container
    return await _run_cmd(
        "messages.react",
        {"channel_id": channel_id, "message_id": message_id, "emoji": body.emoji},
    )


@router.post("/{channel_id}/pins")
async def pin_message(container: ContainerDep, channel_id: str, body: MessagePinBody) -> dict:
    _ = container
    return await _run_cmd(
        "messages.pin",
        {"channel_id": channel_id, "message_id": body.message_id, "action": body.action},
    )


@router.post("/{channel_id}/messages/{message_id}/transcribe")
async def transcribe_audio_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
) -> MessageRead:
    _ = container
    out = await _run_cmd(
        "messages.transcribe_audio",
        {"channel_id": channel_id, "message_id": message_id},
    )
    return MessageRead.model_validate(out)


@router.post("/{channel_id}/messages/{message_id}/transcribe-video")
async def transcribe_video_message(
    container: ContainerDep,
    channel_id: str,
    message_id: str,
) -> MessageRead:
    _ = container
    out = await _run_cmd(
        "messages.transcribe_video",
        {"channel_id": channel_id, "message_id": message_id},
    )
    return MessageRead.model_validate(out)


@router.post("/{channel_id}/calls/{call_id}/transcribe", status_code=202)
async def transcribe_call_session(
    container: ContainerDep,
    channel_id: str,
    call_id: str,
) -> dict[str, str]:
    _ = container
    await _run_cmd_allow_null_result(
        "messages.transcribe_call",
        {"channel_id": channel_id, "call_id": call_id},
    )
    return {"status": "queued"}
