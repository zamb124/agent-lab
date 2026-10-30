"""Platform Sync thread tools — thin wrappers over SyncClient."""

from __future__ import annotations

from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from core.clients.sync_client import SyncClient
from core.clients.sync_models import (
    SyncCreateThreadArgs,
    SyncGetThreadArgs,
    SyncListThreadMessagesArgs,
    SyncListThreadsArgs,
)
from core.types import JsonObject

_TAGS = ["sync"]


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().list_threads(channel_id, limit=limit, offset=offset)


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().get_thread(thread_id)


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().create_thread(
        channel_id, root_message_id=root_message_id, title=title
    )


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().list_thread_messages(
        channel_id, thread_id=thread_id, limit=limit, offset=offset
    )
