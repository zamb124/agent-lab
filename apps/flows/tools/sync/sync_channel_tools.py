"""Platform Sync channel tools — thin wrappers over SyncClient."""

from __future__ import annotations

from typing import Literal

from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from core.clients.sync_client import SyncClient
from core.clients.sync_models import (
    ChannelTypeLiteral,
    SyncAddChannelMemberArgs,
    SyncChannelNotificationSettingsArgs,
    SyncCreateChannelArgs,
    SyncListChannelMembersArgs,
    SyncListChannelsArgs,
    SyncMarkChannelReadArgs,
    SyncUpdateChannelArgs,
)
from core.types import JsonObject

_TAGS = ["sync"]


@tool(
    name="sync_list_channels",
    description=(
        "Lists Sync channels where the current actor is a member (sidebar). "
        "First step after inbox wake when channel_id is unknown, or for «my chats». "
        "Returns items[] with channel_id, type, name/peer, unread, last_message preview."
    ),
    tags=_TAGS,
    parameters_model=SyncListChannelsArgs,
)
async def sync_list_channels(
    namespace: str | None = None,
    limit: int = 50,
    offset: int = 0,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().list_channels(namespace, limit=limit, offset=offset)


@tool(
    name="sync_list_channel_members",
    description=(
        "Lists members of a Sync channel. Use before @mention or add_member. "
        "Not company roster — that is team_list_members. Returns items[] with user_id, role."
    ),
    tags=_TAGS,
    parameters_model=SyncListChannelMembersArgs,
)
async def sync_list_channel_members(
    channel_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().list_channel_members(channel_id)


@tool(
    name="sync_mark_channel_read",
    description=(
        "Marks the channel root lane as read for the current actor "
        "(updates last_read_at / clears unread_count). "
        "Call after reading messages. Returns channel_id."
    ),
    tags=_TAGS,
    parameters_model=SyncMarkChannelReadArgs,
)
async def sync_mark_channel_read(
    channel_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().mark_channel_read(channel_id)


@tool(
    name="sync_create_channel",
    description=(
        "Creates a Sync channel: type=direct (DM with one peer user_id) or type=topic. "
        "Resolve peer via team_resolve_user first. Returns channel brief."
    ),
    tags=_TAGS,
    parameters_model=SyncCreateChannelArgs,
)
async def sync_create_channel(
    type: ChannelTypeLiteral,
    name: str | None = None,
    namespace: str | None = None,
    member_ids: list[str] | None = None,
    is_private: bool = False,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().create_channel(
        type,
        name=name,
        namespace=namespace,
        member_ids=member_ids,
        is_private=is_private,
    )


@tool(
    name="sync_update_channel",
    description=(
        "Updates Sync channel name and/or is_private. "
        "Omit fields you do not change. Returns channel brief."
    ),
    tags=_TAGS,
    parameters_model=SyncUpdateChannelArgs,
)
async def sync_update_channel(
    channel_id: str,
    name: str | None = None,
    is_private: bool | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().update_channel(
        channel_id, name=name, is_private=is_private
    )


@tool(
    name="sync_add_channel_member",
    description=(
        "Adds a company member to a Sync channel. "
        "Resolve user_id via team_resolve_user first. Returns member row."
    ),
    tags=_TAGS,
    parameters_model=SyncAddChannelMemberArgs,
)
async def sync_add_channel_member(
    channel_id: str,
    user_id: str,
    role: Literal["member", "admin"] = "member",
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().add_channel_member(
        channel_id, user_id=user_id, role=role
    )


@tool(
    name="sync_channel_notification_settings",
    description=(
        "Mutes or unmutes Sync channel toast notifications for the current actor. "
        "Returns channel_id and notifications_muted."
    ),
    tags=_TAGS,
    parameters_model=SyncChannelNotificationSettingsArgs,
)
async def sync_channel_notification_settings(
    channel_id: str,
    notifications_muted: bool,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await SyncClient().channel_notification_settings(
        channel_id, notifications_muted=notifications_muted
    )
