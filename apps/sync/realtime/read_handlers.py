"""WS read-handlers для Sync (list/get-операции resource-collection и messages).

Эти команды не идут через `execute_command` (там pipeline для мутаций), а
напрямую читают репозитории и возвращают тот же DTO, что и REST-зеркало:

  - `sync/spaces/list_requested`     -> { items: SpaceRead[] }
  - `sync/channels/list_requested`   -> { items: ChannelRead[] }
  - `sync/threads/list_requested`    -> { items: ThreadRow[] }
  - `sync/threads/item_requested`    -> ThreadRow
  - `sync/messages/list_requested`   -> { items: MessageRead[],
                                          next_cursor, prev_cursor }

Резолвятся payload-ы строго: каждое отсутствующее поле — `WsCommandError`.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from apps.sync.channel_read_helpers import channel_read_from_entity
from apps.sync.container import get_sync_container
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.channels import ChannelRead
from apps.sync.models.common import UserBrief
from apps.sync.models.messages import MessageContentModel, MessageRead
from apps.sync.models.spaces import SpaceRead
from apps.sync.models.threads import ThreadRow
from core.context import get_context
from core.logging import get_logger
from core.models.identity_models import User
from core.websocket import WsCommandError, register_ws_command_handler

logger = get_logger(__name__)

_DEFAULT_LIST_LIMIT = 200
_DEFAULT_MESSAGES_LIMIT = 50


def _resolve_company_id(user: User) -> str:
    context = get_context()
    if context and context.active_company:
        return context.active_company.company_id
    if user.active_company_id:
        return user.active_company_id
    raise WsCommandError("ws_no_company", "Нет active_company_id для read-команды Sync.")


def _decode_message_cursor(cursor: str) -> tuple[datetime, str]:
    padded = cursor + ("=" * ((4 - len(cursor) % 4) % 4))
    raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise WsCommandError("ws_invalid_cursor", "cursor payload must be object")
    sent_at_raw = payload.get("sent_at")
    message_id = payload.get("message_id")
    if not isinstance(sent_at_raw, str) or not sent_at_raw:
        raise WsCommandError("ws_invalid_cursor", "cursor.sent_at required")
    if not isinstance(message_id, str) or not message_id:
        raise WsCommandError("ws_invalid_cursor", "cursor.message_id required")
    return datetime.fromisoformat(sent_at_raw), message_id


def _encode_message_cursor(*, sent_at: datetime, message_id: str) -> str:
    payload = {"sent_at": sent_at.isoformat(), "message_id": message_id}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


async def handle_spaces_list(payload: dict[str, Any], user: User) -> dict[str, Any]:
    company_id = _resolve_company_id(user)
    limit = payload.get("limit") if isinstance(payload, dict) else None
    if not isinstance(limit, int) or limit <= 0:
        limit = _DEFAULT_LIST_LIMIT
    container = get_sync_container()
    spaces = await container.space_repository.list(limit=limit, offset=0, company_id=company_id)
    items = [
        SpaceRead(
            id=s.space_id,
            name=s.name,
            description=s.description,
            avatar_url=s.avatar_url,
            namespace=s.namespace,
            created_at=s.created_at,
            created_by_user_id=s.created_by_user_id,
            transcribe_voice_messages=s.transcribe_voice_messages,
            speech_to_chat_enabled=s.speech_to_chat_enabled,
        ).model_dump(mode="json")
        for s in spaces
    ]
    return {"items": items}


async def handle_channels_list(payload: dict[str, Any], user: User) -> dict[str, Any]:
    company_id = _resolve_company_id(user)
    space_id = payload.get("space_id") if isinstance(payload, dict) else None
    if space_id is not None and (not isinstance(space_id, str) or not space_id):
        raise WsCommandError("ws_invalid_payload", "space_id must be non-empty string or null")
    limit = payload.get("limit") if isinstance(payload, dict) else None
    if not isinstance(limit, int) or limit <= 0:
        limit = _DEFAULT_LIST_LIMIT
    container = get_sync_container()
    channels = await container.channel_repository.list_for_user(
        user.user_id,
        space_id=space_id,
        limit=limit,
        offset=0,
        company_id=company_id,
    )
    channel_ids = [c.channel_id for c in channels]
    summaries = await container.message_repository.channel_lane_summaries_batch(
        company_id=company_id,
        channel_ids=channel_ids,
        viewer_user_id=user.user_id,
    )
    items: list[dict[str, Any]] = []
    for c in channels:
        read = await channel_read_from_entity(
            c,
            viewer_user_id=user.user_id,
            channel_repository=container.channel_repository,
            user_repository=container.user_repository,
            company_id=company_id,
            lane_summary=summaries[c.channel_id],
        )
        items.append(read.model_dump(mode="json"))
    return {"items": items}


async def handle_threads_list(payload: dict[str, Any], user: User) -> dict[str, Any]:
    company_id = _resolve_company_id(user)
    if not isinstance(payload, dict):
        raise WsCommandError("ws_invalid_payload", "payload must be object")
    channel_id = payload.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id:
        raise WsCommandError("ws_invalid_payload", "channel_id required (non-empty string)")
    limit = payload.get("limit")
    if not isinstance(limit, int) or limit <= 0:
        limit = _DEFAULT_LIST_LIMIT
    container = get_sync_container()
    threads = await container.thread_repository.list_by_channel(
        channel_id,
        limit=limit,
        company_id=company_id,
    )
    items = [
        ThreadRow(
            id=t.thread_id,
            channel_id=t.channel_id,
            root_message_id=t.root_message_id,
            title=t.title,
            created_at=t.created_at,
            created_by_user_id=t.created_by_user_id,
        ).model_dump(mode="json")
        for t in threads
    ]
    return {"items": items}


async def handle_thread_item(payload: dict[str, Any], user: User) -> dict[str, Any]:
    _ = _resolve_company_id(user)
    if not isinstance(payload, dict):
        raise WsCommandError("ws_invalid_payload", "payload must be object")
    thread_id = payload.get("id") or payload.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        raise WsCommandError("ws_invalid_payload", "id required (non-empty string)")
    container = get_sync_container()
    thread = await container.thread_repository.get(thread_id)
    if thread is None:
        raise WsCommandError("not_found", f"Thread {thread_id!r} not found.")
    return ThreadRow(
        id=thread.thread_id,
        channel_id=thread.channel_id,
        root_message_id=thread.root_message_id,
        title=thread.title,
        created_at=thread.created_at,
        created_by_user_id=thread.created_by_user_id,
    ).model_dump(mode="json")


async def handle_messages_list(payload: dict[str, Any], user: User) -> dict[str, Any]:
    company_id = _resolve_company_id(user)
    if not isinstance(payload, dict):
        raise WsCommandError("ws_invalid_payload", "payload must be object")
    channel_id = payload.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id:
        raise WsCommandError("ws_invalid_payload", "channel_id required (non-empty string)")
    limit = payload.get("limit")
    if not isinstance(limit, int) or limit <= 0:
        limit = _DEFAULT_MESSAGES_LIMIT
    before_raw = payload.get("before")
    after_raw = payload.get("after")
    if before_raw is not None and after_raw is not None:
        raise WsCommandError("ws_invalid_payload", "before and after are mutually exclusive")

    before_sent_at = before_message_id = None
    if isinstance(before_raw, str) and before_raw:
        before_sent_at, before_message_id = _decode_message_cursor(before_raw)
    after_sent_at = after_message_id = None
    if isinstance(after_raw, str) and after_raw:
        after_sent_at, after_message_id = _decode_message_cursor(after_raw)

    container = get_sync_container()
    window = await container.message_repository.list_by_channel_cursor(
        channel_id=channel_id,
        limit=limit,
        before_sent_at=before_sent_at,
        before_message_id=before_message_id,
        after_sent_at=after_sent_at,
        after_message_id=after_message_id,
        company_id=company_id,
    )
    rows = window.rows
    if not rows:
        return {"items": [], "next_cursor": None, "prev_cursor": None}

    user_ids = list({m.sender_user_id for m in rows})
    users_by_id = await container.user_repository.get_many(user_ids)

    chronological = list(reversed(rows))
    items: list[dict[str, Any]] = []
    for m in chronological:
        content_rows = await container.message_repository.list_contents(m.message_id)
        contents = [
            MessageContentModel.model_validate(
                {"type": row.type, "data": row.data, "order": row.order}
            )
            for row in content_rows
        ]
        u = users_by_id.get(m.sender_user_id)
        if u is None:
            sender = UserBrief(
                user_id=m.sender_user_id,
                display_name=m.sender_user_id,
                avatar_url=None,
            )
        else:
            sender = UserBrief(user_id=m.sender_user_id, display_name=u.name, avatar_url=u.avatar_url)
        items.append(
            message_read_from_entity(m=m, contents=contents, sender=sender).model_dump(mode="json")
        )

    oldest = chronological[0]
    newest = chronological[-1]
    next_cursor = (
        _encode_message_cursor(sent_at=oldest.sent_at, message_id=oldest.message_id)
        if window.has_more_older
        else None
    )
    prev_cursor = (
        _encode_message_cursor(sent_at=newest.sent_at, message_id=newest.message_id)
        if window.has_more_newer
        else None
    )
    return {"items": items, "next_cursor": next_cursor, "prev_cursor": prev_cursor}


_READ_HANDLERS: dict[str, Any] = {
    "sync/spaces/list_requested": handle_spaces_list,
    "sync/channels/list_requested": handle_channels_list,
    "sync/threads/list_requested": handle_threads_list,
    "sync/threads/item_requested": handle_thread_item,
    "sync/messages/list_requested": handle_messages_list,
}


def register_sync_ws_read_handlers() -> None:
    """Зарегистрировать read-команды Sync. Вызывать на on_startup."""
    for command_type, handler in _READ_HANDLERS.items():
        register_ws_command_handler(command_type, handler)
    logger.info(
        "Sync WS read-handlers зарегистрированы (%d команд)", len(_READ_HANDLERS)
    )
