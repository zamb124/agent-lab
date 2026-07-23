"""Sync channel tools для flow-сотрудника / Lara."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient
from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

_TAGS = ["misc", "sync"]
ChannelTypeLiteral = Literal["direct", "topic"]


class SyncListChannelsArgs(StrictBaseModel):
    namespace: str | None = Field(
        default=None,
        description="Фильтр company_workspace namespace. Omit — все membership-каналы.",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Лимит (1–200).")
    offset: int = Field(default=0, ge=0, description="Offset пагинации.")


class SyncListChannelMembersArgs(StrictBaseModel):
    channel_id: str = Field(
        ...,
        min_length=1,
        description="channel_id из sync_list_channels / context.",
    )


class SyncMarkChannelReadArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id для mark_read.")


class SyncCreateChannelArgs(StrictBaseModel):
    type: ChannelTypeLiteral = Field(
        ...,
        description="direct (нужен ровно один peer в member_ids) или topic (нужны name + namespace).",
    )
    name: str | None = Field(
        default=None,
        description="Имя topic-канала. Для direct обычно omit.",
    )
    namespace: str | None = Field(
        default=None,
        description="Для topic обязателен. Для direct omit → default.",
    )
    member_ids: list[str] | None = Field(
        default=None,
        description=(
            "Для direct — ровно один peer user_id из team_resolve_user. "
            "Для topic — опционально доп. участники."
        ),
    )
    is_private: bool = Field(default=False, description="Приватный topic.")


class SyncUpdateChannelArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id для update.")
    name: str | None = Field(default=None, description="Новое имя. Omit — не менять.")
    is_private: bool | None = Field(
        default=None, description="Новый флаг приватности. Omit — не менять."
    )


class SyncAddChannelMemberArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id.")
    user_id: str = Field(
        ...,
        min_length=1,
        description="user_id из team_resolve_user / team_list_members. Не выдумывай.",
    )
    role: Literal["member", "admin"] = Field(
        default="member",
        description="Роль участника: member|admin.",
    )


class SyncChannelNotificationSettingsArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="channel_id.")
    notifications_muted: bool = Field(
        ...,
        description="true — mute канальных тостов; false — unmute.",
    )


def _channel_brief(raw: JsonObject) -> JsonObject:
    peer = raw.get("peer")
    peer_user_id = None
    if isinstance(peer, dict):
        peer_raw = peer.get("user_id")
        if isinstance(peer_raw, str):
            peer_user_id = peer_raw
    return {
        "channel_id": raw.get("channel_id"),
        "type": raw.get("type"),
        "name": raw.get("name"),
        "namespace": raw.get("namespace"),
        "peer_user_id": peer_user_id,
        "unread_count": raw.get("unread_count"),
        "mention_unread_count": raw.get("mention_unread_count"),
        "last_message_preview": raw.get("last_message_preview"),
        "last_message_at": raw.get("last_message_at"),
    }


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
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncListChannelsArgs(namespace=namespace, limit=limit, offset=offset)
    params: dict[str, str] = {
        "limit": str(args.limit),
        "offset": str(args.offset),
    }
    if args.namespace is not None:
        params["namespace"] = args.namespace
    client = ServiceClient()
    response = await client.get("sync", "/sync/api/v1/channels/", params=params)
    result = require_json_object(response, "sync_list_channels.response")
    raw_items = result.get("items")
    items: list[JsonObject] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                items.append(_channel_brief(require_json_object(item, "channel")))
    return {
        "items": items,
        "total": result.get("total"),
        "limit": result.get("limit"),
        "offset": result.get("offset"),
    }


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
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncListChannelMembersArgs(channel_id=channel_id)
    client = ServiceClient()
    response = await client.get(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/members",
    )
    result = require_json_object(response, "sync_list_channel_members.response")
    raw_items = result.get("items")
    items: list[JsonObject] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                items.append(
                    {
                        "user_id": item.get("user_id"),
                        "role": item.get("role"),
                    }
                )
    return {"channel_id": args.channel_id, "items": items}


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
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncMarkChannelReadArgs(channel_id=channel_id)
    client = ServiceClient()
    _ = await client.post(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/read",
    )
    return {"channel_id": args.channel_id, "read": True}


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
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncCreateChannelArgs(
        type=type,
        name=name,
        namespace=namespace,
        member_ids=member_ids,
        is_private=is_private,
    )
    body: JsonObject = {"type": args.type, "is_private": args.is_private}
    if args.name is not None:
        body["name"] = args.name
    if args.namespace is not None:
        body["namespace"] = args.namespace
    if args.member_ids is not None:
        body["member_ids"] = list(args.member_ids)
    client = ServiceClient()
    response = await client.post("sync", "/sync/api/v1/channels/", json=body)
    result = require_json_object(response, "sync_create_channel.response")
    return _channel_brief(result)


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
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncUpdateChannelArgs(
        channel_id=channel_id, name=name, is_private=is_private
    )
    body: JsonObject = {}
    if args.name is not None:
        body["name"] = args.name
    if args.is_private is not None:
        body["is_private"] = args.is_private
    if not body:
        raise ValueError("Нужен name и/или is_private")
    client = ServiceClient()
    response = await client.patch(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}",
        json=body,
    )
    result = require_json_object(response, "sync_update_channel.response")
    return _channel_brief(result)


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
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncAddChannelMemberArgs(
        channel_id=channel_id, user_id=user_id, role=role
    )
    client = ServiceClient()
    response = await client.post(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/members",
        json={"user_id": args.user_id, "role": args.role},
    )
    result = require_json_object(response, "sync_add_channel_member.response")
    return {
        "channel_id": args.channel_id,
        "user_id": result.get("user_id"),
        "role": result.get("role"),
    }


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
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = SyncChannelNotificationSettingsArgs(
        channel_id=channel_id,
        notifications_muted=notifications_muted,
    )
    client = ServiceClient()
    response = await client.patch(
        "sync",
        f"/sync/api/v1/channels/{args.channel_id}/notification-settings",
        json={"notifications_muted": args.notifications_muted},
    )
    result = require_json_object(response, "sync_channel_notification_settings.response")
    return {
        "channel_id": args.channel_id,
        "notifications_muted": result.get("notifications_muted", args.notifications_muted),
    }
