"""Sync thread tools для flow-сотрудника / Lara."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from apps.flows.tools.sync_tools import sync_message_brief
from core.clients.service_client import ServiceClient
from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

_TAGS = ["misc", "sync"]


class SyncListThreadsArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id владельца тредов.")
    limit: int = Field(default=50, ge=1, le=200, description="Лимит.")
    offset: int = Field(default=0, ge=0, description="Offset.")


class SyncGetThreadArgs(StrictBaseModel):
    thread_id: str = Field(..., min_length=1, description="thread_id из list/create.")


class SyncCreateThreadArgs(StrictBaseModel):
    channel_id: str = Field(
        ...,
        min_length=1,
        description="channel_id (для REST path; сервер берёт канал из root message).",
    )
    root_message_id: str = Field(
        ...,
        min_length=1,
        description="message_id корневого сообщения ленты для нового треда.",
    )
    title: str | None = Field(default=None, description="Опциональный заголовок треда.")


class SyncListThreadMessagesArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id треда.")
    thread_id: str = Field(..., min_length=1, description="thread_id.")
    limit: int = Field(default=50, ge=1, le=200, description="Лимит сообщений.")
    offset: int = Field(default=0, ge=0, description="Offset.")


def _thread_brief(raw: JsonObject) -> JsonObject:
    created_by_user_id = raw.get("created_by_user_id")
    if not isinstance(created_by_user_id, str):
        created_by = raw.get("created_by")
        if isinstance(created_by, dict):
            nested_user_id = created_by.get("user_id")
            created_by_user_id = nested_user_id if isinstance(nested_user_id, str) else None
        else:
            created_by_user_id = None
    return {
        "thread_id": raw.get("thread_id"),
        "channel_id": raw.get("channel_id"),
        "root_message_id": raw.get("root_message_id"),
        "title": raw.get("title"),
        "created_at": raw.get("created_at"),
        "created_by_user_id": created_by_user_id,
    }


@tool(
    name="sync_list_threads",
    description=(
        "Lists threads in a Sync channel. Use before reading thread history. "
        "Returns items[] with thread_id, root_message_id, title."
    ),
    tags=_TAGS,
    parameters_model=SyncListThreadsArgs,
)
async def sync_list_threads(
    channel_id: str,
    limit: int = 50,
    offset: int = 0,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncListThreadsArgs(channel_id=channel_id, limit=limit, offset=offset)
    client = ServiceClient()
    response = await client.get(
        "sync",
        "/sync/api/v1/threads/",
        params={
            "channel_id": args.channel_id,
            "limit": str(args.limit),
            "offset": str(args.offset),
        },
    )
    result = require_json_object(response, "sync_list_threads.response")
    raw_items = result.get("items")
    items: list[JsonObject] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                items.append(_thread_brief(require_json_object(item, "thread")))
    return {
        "channel_id": args.channel_id,
        "items": items,
        "total": result.get("total"),
        "limit": result.get("limit"),
        "offset": result.get("offset"),
    }


@tool(
    name="sync_get_thread",
    description=(
        "Gets one Sync thread by thread_id. Returns thread_id, channel_id, root_message_id."
    ),
    tags=_TAGS,
    parameters_model=SyncGetThreadArgs,
)
async def sync_get_thread(
    thread_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncGetThreadArgs(thread_id=thread_id)
    client = ServiceClient()
    response = await client.get(
        "sync",
        f"/sync/api/v1/threads/{args.thread_id}",
    )
    result = require_json_object(response, "sync_get_thread.response")
    return _thread_brief(result)


@tool(
    name="sync_create_thread",
    description=(
        "Creates a Sync thread from a root_message_id in the channel lane. "
        "Then send replies with sync_send_message(thread_id=...). Returns thread brief."
    ),
    tags=_TAGS,
    parameters_model=SyncCreateThreadArgs,
)
async def sync_create_thread(
    channel_id: str,
    root_message_id: str,
    title: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncCreateThreadArgs(
        channel_id=channel_id,
        root_message_id=root_message_id,
        title=title,
    )
    body: JsonObject = {"root_message_id": args.root_message_id}
    if args.title is not None:
        body["title"] = args.title
    client = ServiceClient()
    response = await client.post(
        "sync",
        "/sync/api/v1/threads/",
        params={"channel_id": args.channel_id},
        json=body,
    )
    result = require_json_object(response, "sync_create_thread.response")
    return _thread_brief(result)


@tool(
    name="sync_list_thread_messages",
    description=(
        "Lists messages inside a Sync thread (not the root lane). "
        "Use after sync_list_threads / sync_get_thread. "
        "Do not use sync_list_messages for thread history. "
        "Returns items[] with message_id, text_preview, sender."
    ),
    tags=_TAGS,
    parameters_model=SyncListThreadMessagesArgs,
)
async def sync_list_thread_messages(
    channel_id: str,
    thread_id: str,
    limit: int = 50,
    offset: int = 0,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncListThreadMessagesArgs(
        channel_id=channel_id,
        thread_id=thread_id,
        limit=limit,
        offset=offset,
    )
    client = ServiceClient()
    response = await client.get(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/threads/{args.thread_id}/messages",
        params={"limit": str(args.limit), "offset": str(args.offset)},
    )
    result = require_json_object(response, "sync_list_thread_messages.response")
    raw_items = result.get("items")
    items: list[JsonObject] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                items.append(sync_message_brief(require_json_object(item, "message")))
    return {
        "channel_id": args.channel_id,
        "thread_id": args.thread_id,
        "count": len(items),
        "items": items,
        "total": result.get("total"),
        "limit": result.get("limit"),
        "offset": result.get("offset"),
    }
