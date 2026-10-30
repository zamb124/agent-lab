"""Platform Sync messaging tools — thin wrappers over SyncClient."""

from __future__ import annotations

from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from core.clients.sync_client import SyncClient
from core.clients.sync_models import (
    SyncDeleteMessageArgs,
    SyncEditMessageArgs,
    SyncListMessagesArgs,
    SyncMarkMessageReadArgs,
    SyncReactMessageArgs,
    SyncSendMessageArgs,
)
from core.types import JsonObject

_TAGS = ["sync"]

__all__ = [
    "sync_list_messages",
    "sync_send_message",
    "sync_edit_message",
    "sync_delete_message",
    "sync_react_message",
    "sync_mark_message_read",
]


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().list_messages(
        channel_id, limit=limit, before=before, after=after
    )


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().send_message(
        channel_id,
        text=text,
        thread_id=thread_id,
        parent_message_id=parent_message_id,
        mentioned_user_ids=mentioned_user_ids,
    )


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().edit_message(channel_id, message_id=message_id, text=text)


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().delete_message(channel_id, message_id=message_id)


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().react_message(channel_id, message_id=message_id, emoji=emoji)


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().mark_message_read(channel_id, message_id=message_id)
