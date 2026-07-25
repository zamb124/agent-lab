"""Платформенные тулы Sync messaging для flow-сотрудника / Lara.

Сотрудник действует от собственного имени (Context.user = employee, SESSION JWT),
поэтому ServiceClient проходит обычный auth и ACL канала штатно.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient
from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

_TAGS = ["sync"]


class SyncListMessagesArgs(StrictBaseModel):
    channel_id: str = Field(
        ...,
        min_length=1,
        description="channel_id из sync_list_channels / UI context / inbox. Не выдумывай.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Сколько сообщений корневой ленты вернуть (1–200).",
    )
    before: str | None = Field(
        default=None,
        description="Opaque cursor next_cursor — страница старше. Не вместе с after.",
    )
    after: str | None = Field(
        default=None,
        description="Opaque cursor prev_cursor — страница новее. Не вместе с before.",
    )


class SyncSendMessageArgs(StrictBaseModel):
    channel_id: str = Field(
        ...,
        min_length=1,
        description="channel_id назначения. Только из tools/context.",
    )
    text: str = Field(
        ...,
        min_length=1,
        description="Текст text/plain (Markdown). Не шлай без явной просьбы пользователя.",
    )
    thread_id: str | None = Field(
        default=None,
        description="thread_id для ответа в тред. Omit — корневая лента.",
    )
    parent_message_id: str | None = Field(
        default=None,
        description="message_id, на которое отвечаем в ленте (не путать с thread_id).",
    )
    mentioned_user_ids: list[str] | None = Field(
        default=None,
        description=(
            "user_id участников для @mention — только из team_resolve_user / "
            "team_list_members / sync_list_channel_members. Нужен чтобы разбудить "
            "коллегу в group (симметрично inbox-контракту)."
        ),
    )


class SyncEditMessageArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id сообщения.")
    message_id: str = Field(..., min_length=1, description="message_id из list/send.")
    text: str = Field(..., min_length=1, description="Новый текст text/plain.")


class SyncDeleteMessageArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id сообщения.")
    message_id: str = Field(..., min_length=1, description="message_id для soft-delete.")


class SyncReactMessageArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id сообщения.")
    message_id: str = Field(..., min_length=1, description="message_id из list.")
    emoji: str | None = Field(
        default=None,
        description="Emoji-реакция. null/omit — снять свою реакцию.",
    )


class SyncMarkMessageReadArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id.")
    message_id: str = Field(..., min_length=1, description="message_id для status read.")


def sync_message_brief(raw: JsonObject) -> JsonObject:
    contents = raw.get("contents")
    preview = ""
    if isinstance(contents, list):
        for block in contents:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text/plain":
                continue
            data = block.get("data")
            if isinstance(data, dict):
                body = data.get("body")
                if isinstance(body, str):
                    preview = body
                    break
    sender_user_id = raw.get("sender_user_id")
    if not isinstance(sender_user_id, str):
        sender = raw.get("sender")
        if isinstance(sender, dict):
            nested_user_id = sender.get("user_id")
            sender_user_id = nested_user_id if isinstance(nested_user_id, str) else None
        else:
            sender_user_id = None
    return {
        "message_id": raw.get("message_id"),
        "channel_id": raw.get("channel_id"),
        "thread_id": raw.get("thread_id"),
        "parent_message_id": raw.get("parent_message_id"),
        "sender_user_id": sender_user_id,
        "sent_at": raw.get("sent_at"),
        "text_preview": preview,
        "contents": contents if isinstance(contents, list) else [],
    }


@tool(
    name="sync_list_messages",
    description=(
        "Lists root-lane messages of a Sync channel (thread_id IS NULL). "
        "Use after inbox wake or when summarizing a channel. "
        "Do not use for channel discovery — call sync_list_channels. "
        "Do not use for thread history — call sync_list_thread_messages. "
        "Optional before/after cursors from previous response. "
        "Returns items[] with message_id, text_preview, sender, cursors."
    ),
    tags=_TAGS,
    parameters_model=SyncListMessagesArgs,
)
async def sync_list_messages(
    channel_id: str,
    limit: int = 20,
    before: str | None = None,
    after: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncListMessagesArgs(
        channel_id=channel_id, limit=limit, before=before, after=after
    )
    if args.before is not None and args.after is not None:
        raise ValueError("before и after взаимоисключающи")
    params: dict[str, str] = {"limit": str(args.limit)}
    if args.before is not None:
        params["before"] = args.before
    if args.after is not None:
        params["after"] = args.after
    client = ServiceClient()
    response = await client.get(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/messages",
        params=params,
    )
    result = require_json_object(response, "sync_list_messages.response")
    raw_items = result.get("items")
    items_out: list[JsonObject] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                items_out.append(sync_message_brief(require_json_object(item, "message")))
    return {
        "channel_id": args.channel_id,
        "count": len(items_out),
        "items": items_out,
        "next_cursor": result.get("next_cursor"),
        "prev_cursor": result.get("prev_cursor"),
    }


@tool(
    name="sync_send_message",
    description=(
        "Sends a text/plain Sync message as the current actor (flow employee JWT). "
        "Call only when the user explicitly asked to send. "
        "For @mention in groups pass mentioned_user_ids from team_resolve_user "
        "(wakes colleagues). Optional thread_id / parent_message_id. "
        "Returns message_id, channel_id."
    ),
    tags=_TAGS,
    parameters_model=SyncSendMessageArgs,
)
async def sync_send_message(
    channel_id: str,
    text: str,
    thread_id: str | None = None,
    parent_message_id: str | None = None,
    mentioned_user_ids: list[str] | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncSendMessageArgs(
        channel_id=channel_id,
        text=text,
        thread_id=thread_id,
        parent_message_id=parent_message_id,
        mentioned_user_ids=mentioned_user_ids,
    )
    payload: JsonObject = {
        "contents": [{"type": "text/plain", "order": 0, "data": {"body": args.text}}],
    }
    if args.thread_id is not None:
        payload["thread_id"] = args.thread_id
    if args.parent_message_id is not None:
        payload["parent_message_id"] = args.parent_message_id
    if args.mentioned_user_ids is not None:
        payload["mentioned_user_ids"] = list(args.mentioned_user_ids)
    client = ServiceClient()
    response = await client.post(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/messages",
        json=payload,
    )
    result = require_json_object(response, "sync_send_message.response")
    message_id = result.get("message_id")
    if not isinstance(message_id, str) or not message_id.strip():
        raise ValueError("sync_send_message: response missing message_id")
    return {"message_id": message_id, "channel_id": args.channel_id}


@tool(
    name="sync_edit_message",
    description=(
        "Edits own Sync message text (full contents replace with one text/plain). "
        "Use message_id from list/send. Returns updated message brief."
    ),
    tags=_TAGS,
    parameters_model=SyncEditMessageArgs,
)
async def sync_edit_message(
    channel_id: str,
    message_id: str,
    text: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncEditMessageArgs(channel_id=channel_id, message_id=message_id, text=text)
    client = ServiceClient()
    response = await client.patch(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/messages/{args.message_id}",
        json={
            "contents": [
                {"type": "text/plain", "order": 0, "data": {"body": args.text}}
            ]
        },
    )
    result = require_json_object(response, "sync_edit_message.response")
    return sync_message_brief(result)


@tool(
    name="sync_delete_message",
    description=(
        "Soft-deletes a Sync message by message_id (usually own). "
        "Not for hiding history from others without cause. Returns message_id."
    ),
    tags=_TAGS,
    parameters_model=SyncDeleteMessageArgs,
)
async def sync_delete_message(
    channel_id: str,
    message_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncDeleteMessageArgs(channel_id=channel_id, message_id=message_id)
    client = ServiceClient()
    _ = await client.delete(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/messages/{args.message_id}",
    )
    return {"message_id": args.message_id, "channel_id": args.channel_id, "deleted": True}


@tool(
    name="sync_react_message",
    description=(
        "Adds or clears an emoji reaction on a Sync message. "
        "Pass emoji to set; omit/null emoji to clear own reaction. "
        "Returns message brief with reactions."
    ),
    tags=_TAGS,
    parameters_model=SyncReactMessageArgs,
)
async def sync_react_message(
    channel_id: str,
    message_id: str,
    emoji: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncReactMessageArgs(
        channel_id=channel_id, message_id=message_id, emoji=emoji
    )
    body: JsonObject = {"emoji": args.emoji}
    client = ServiceClient()
    response = await client.post(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/messages/{args.message_id}/react",
        json=body,
    )
    result = require_json_object(response, "sync_react_message.response")
    return sync_message_brief(result)


@tool(
    name="sync_mark_message_read",
    description=(
        "Marks a specific message as read (status event). "
        "Does not clear channel unread_count — use sync_mark_channel_read for that. "
        "Returns message_id."
    ),
    tags=_TAGS,
    parameters_model=SyncMarkMessageReadArgs,
)
async def sync_mark_message_read(
    channel_id: str,
    message_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncMarkMessageReadArgs(channel_id=channel_id, message_id=message_id)
    client = ServiceClient()
    _ = await client.post(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/messages/{args.message_id}/read",
    )
    return {"message_id": args.message_id, "channel_id": args.channel_id, "read": True}
