"""HTTP client for Sync API on top of ServiceClient."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from core.clients.service_client import ServiceClient
from core.clients.sync_models import (
    ChannelTypeLiteral,
    SyncAddChannelMemberArgs,
    SyncChannelNotificationSettingsArgs,
    SyncCreateChannelArgs,
    SyncCreateThreadArgs,
    SyncDeleteMessageArgs,
    SyncEditMessageArgs,
    SyncGetThreadArgs,
    SyncListChannelMembersArgs,
    SyncListChannelsArgs,
    SyncListMessagesArgs,
    SyncListThreadMessagesArgs,
    SyncListThreadsArgs,
    SyncMarkChannelReadArgs,
    SyncMarkMessageReadArgs,
    SyncReactMessageArgs,
    SyncSendMessageArgs,
    SyncUpdateChannelArgs,
)
from core.types import JsonObject, JsonValue, require_json_array, require_json_object

_API = "/sync/api/v1"


class SyncClient:
    """REST client for sync messaging / channels / threads."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    @staticmethod
    def message_brief(raw: JsonObject) -> JsonObject:
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

    @staticmethod
    def channel_brief(raw: JsonObject) -> JsonObject:
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

    @staticmethod
    def thread_brief(raw: JsonObject) -> JsonObject:
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

    @staticmethod
    def _as_objects(value: JsonValue, label: str) -> list[JsonObject]:
        items = require_json_array(value, label)
        return [require_json_object(item, f"{label}[{index}]") for index, item in enumerate(items)]

    async def list_messages(
        self,
        channel_id: str | SyncListMessagesArgs,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
    ) -> JsonObject:
        if isinstance(channel_id, SyncListMessagesArgs):
            args = channel_id
        else:
            args = SyncListMessagesArgs(
                channel_id=channel_id, limit=limit, before=before, after=after
            )
        if args.before is not None and args.after is not None:
            raise ValueError("before and after are mutually exclusive")
        params: dict[str, str] = {"limit": str(args.limit)}
        if args.before is not None:
            params["before"] = args.before
        if args.after is not None:
            params["after"] = args.after
        response = await self._http.get(
            "sync",
            f"{_API}/channels/{quote(args.channel_id, safe='')}/messages",
            params=params,
        )
        result = require_json_object(response, "sync.list_messages")
        items_out = [
            self.message_brief(item)
            for item in self._as_objects(result.get("items"), "sync.list_messages.items")
        ]
        return {
            "channel_id": args.channel_id,
            "count": len(items_out),
            "items": items_out,
            "next_cursor": result.get("next_cursor"),
            "prev_cursor": result.get("prev_cursor"),
        }

    async def send_message(
        self,
        channel_id: str | SyncSendMessageArgs,
        text: str = "",
        thread_id: str | None = None,
        parent_message_id: str | None = None,
        mentioned_user_ids: list[str] | None = None,
    ) -> JsonObject:
        if isinstance(channel_id, SyncSendMessageArgs):
            args = channel_id
        else:
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
        response = await self._http.post(
            "sync",
            f"{_API}/channels/{quote(args.channel_id, safe='')}/messages",
            json=payload,
        )
        result = require_json_object(response, "sync.send_message")
        message_id = result.get("message_id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("sync.send_message: response missing message_id")
        return {"message_id": message_id, "channel_id": args.channel_id}

    async def edit_message(
        self,
        channel_id: str | SyncEditMessageArgs,
        message_id: str = "",
        text: str = "",
    ) -> JsonObject:
        if isinstance(channel_id, SyncEditMessageArgs):
            args = channel_id
        else:
            args = SyncEditMessageArgs(channel_id=channel_id, message_id=message_id, text=text)
        response = await self._http.patch(
            "sync",
            (
                f"{_API}/channels/{quote(args.channel_id, safe='')}"
                f"/messages/{quote(args.message_id, safe='')}"
            ),
            json={
                "contents": [
                    {"type": "text/plain", "order": 0, "data": {"body": args.text}}
                ]
            },
        )
        result = require_json_object(response, "sync.edit_message")
        return self.message_brief(result)

    async def delete_message(
        self,
        channel_id: str | SyncDeleteMessageArgs,
        message_id: str = "",
    ) -> JsonObject:
        if isinstance(channel_id, SyncDeleteMessageArgs):
            args = channel_id
        else:
            args = SyncDeleteMessageArgs(channel_id=channel_id, message_id=message_id)
        _ = await self._http.delete(
            "sync",
            (
                f"{_API}/channels/{quote(args.channel_id, safe='')}"
                f"/messages/{quote(args.message_id, safe='')}"
            ),
        )
        return {"message_id": args.message_id, "channel_id": args.channel_id, "deleted": True}

    async def react_message(
        self,
        channel_id: str | SyncReactMessageArgs,
        message_id: str = "",
        emoji: str | None = None,
    ) -> JsonObject:
        if isinstance(channel_id, SyncReactMessageArgs):
            args = channel_id
        else:
            args = SyncReactMessageArgs(
                channel_id=channel_id, message_id=message_id, emoji=emoji
            )
        response = await self._http.post(
            "sync",
            (
                f"{_API}/channels/{quote(args.channel_id, safe='')}"
                f"/messages/{quote(args.message_id, safe='')}/react"
            ),
            json={
                "channel_id": args.channel_id,
                "message_id": args.message_id,
                "emoji": args.emoji,
            },
        )
        result = require_json_object(response, "sync.react_message")
        return self.message_brief(result)

    async def mark_message_read(
        self,
        channel_id: str | SyncMarkMessageReadArgs,
        message_id: str = "",
    ) -> JsonObject:
        if isinstance(channel_id, SyncMarkMessageReadArgs):
            args = channel_id
        else:
            args = SyncMarkMessageReadArgs(channel_id=channel_id, message_id=message_id)
        _ = await self._http.post(
            "sync",
            (
                f"{_API}/channels/{quote(args.channel_id, safe='')}"
                f"/messages/{quote(args.message_id, safe='')}/read"
            ),
        )
        return {"message_id": args.message_id, "channel_id": args.channel_id, "read": True}

    async def list_channels(
        self,
        namespace: str | SyncListChannelsArgs | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JsonObject:
        if isinstance(namespace, SyncListChannelsArgs):
            args = namespace
        else:
            args = SyncListChannelsArgs(namespace=namespace, limit=limit, offset=offset)
        params: dict[str, str] = {
            "limit": str(args.limit),
            "offset": str(args.offset),
        }
        if args.namespace is not None:
            params["namespace"] = args.namespace
        response = await self._http.get("sync", f"{_API}/channels/", params=params)
        result = require_json_object(response, "sync.list_channels")
        items = [
            self.channel_brief(item)
            for item in self._as_objects(result.get("items"), "sync.list_channels.items")
        ]
        return {
            "items": items,
            "total": result.get("total"),
            "limit": result.get("limit"),
            "offset": result.get("offset"),
        }

    async def list_channel_members(
        self,
        channel_id: str | SyncListChannelMembersArgs,
    ) -> JsonObject:
        if isinstance(channel_id, SyncListChannelMembersArgs):
            args = channel_id
        else:
            args = SyncListChannelMembersArgs(channel_id=channel_id)
        response = await self._http.get(
            "sync",
            f"{_API}/channels/{quote(args.channel_id, safe='')}/members",
        )
        result = require_json_object(response, "sync.list_channel_members")
        items: list[JsonObject] = []
        for item in self._as_objects(result.get("items"), "sync.list_channel_members.items"):
            items.append({"user_id": item.get("user_id"), "role": item.get("role")})
        return {"channel_id": args.channel_id, "items": items}

    async def mark_channel_read(
        self,
        channel_id: str | SyncMarkChannelReadArgs,
    ) -> JsonObject:
        if isinstance(channel_id, SyncMarkChannelReadArgs):
            args = channel_id
        else:
            args = SyncMarkChannelReadArgs(channel_id=channel_id)
        _ = await self._http.post(
            "sync",
            f"{_API}/channels/{quote(args.channel_id, safe='')}/read",
        )
        return {"channel_id": args.channel_id, "read": True}

    async def create_channel(
        self,
        type: ChannelTypeLiteral | SyncCreateChannelArgs = "topic",
        name: str | None = None,
        namespace: str | None = None,
        member_ids: list[str] | None = None,
        is_private: bool = False,
    ) -> JsonObject:
        if isinstance(type, SyncCreateChannelArgs):
            args = type
        else:
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
        response = await self._http.post("sync", f"{_API}/channels/", json=body)
        result = require_json_object(response, "sync.create_channel")
        return self.channel_brief(result)

    async def update_channel(
        self,
        channel_id: str | SyncUpdateChannelArgs,
        name: str | None = None,
        is_private: bool | None = None,
    ) -> JsonObject:
        if isinstance(channel_id, SyncUpdateChannelArgs):
            args = channel_id
        else:
            args = SyncUpdateChannelArgs(
                channel_id=channel_id, name=name, is_private=is_private
            )
        body: JsonObject = {}
        if args.name is not None:
            body["name"] = args.name
        if args.is_private is not None:
            body["is_private"] = args.is_private
        if not body:
            raise ValueError("name and/or is_private is required")
        response = await self._http.patch(
            "sync",
            f"{_API}/channels/{quote(args.channel_id, safe='')}",
            json=body,
        )
        result = require_json_object(response, "sync.update_channel")
        return self.channel_brief(result)

    async def add_channel_member(
        self,
        channel_id: str | SyncAddChannelMemberArgs,
        user_id: str = "",
        role: Literal["member", "admin"] = "member",
    ) -> JsonObject:
        if isinstance(channel_id, SyncAddChannelMemberArgs):
            args = channel_id
        else:
            args = SyncAddChannelMemberArgs(
                channel_id=channel_id,
                user_id=user_id,
                role=role,
            )
        response = await self._http.post(
            "sync",
            f"{_API}/channels/{quote(args.channel_id, safe='')}/members",
            json={"user_id": args.user_id, "role": args.role},
        )
        result = require_json_object(response, "sync.add_channel_member")
        return {
            "channel_id": args.channel_id,
            "user_id": result.get("user_id"),
            "role": result.get("role"),
        }

    async def channel_notification_settings(
        self,
        channel_id: str | SyncChannelNotificationSettingsArgs,
        notifications_muted: bool = False,
    ) -> JsonObject:
        if isinstance(channel_id, SyncChannelNotificationSettingsArgs):
            args = channel_id
        else:
            args = SyncChannelNotificationSettingsArgs(
                channel_id=channel_id,
                notifications_muted=notifications_muted,
            )
        response = await self._http.patch(
            "sync",
            f"{_API}/channels/{quote(args.channel_id, safe='')}/notification-settings",
            json={"notifications_muted": args.notifications_muted},
        )
        result = require_json_object(response, "sync.channel_notification_settings")
        return {
            "channel_id": args.channel_id,
            "notifications_muted": result.get(
                "notifications_muted", args.notifications_muted
            ),
        }

    async def list_threads(
        self,
        channel_id: str | SyncListThreadsArgs,
        limit: int = 50,
        offset: int = 0,
    ) -> JsonObject:
        if isinstance(channel_id, SyncListThreadsArgs):
            args = channel_id
        else:
            args = SyncListThreadsArgs(channel_id=channel_id, limit=limit, offset=offset)
        response = await self._http.get(
            "sync",
            f"{_API}/threads/",
            params={
                "channel_id": args.channel_id,
                "limit": str(args.limit),
                "offset": str(args.offset),
            },
        )
        result = require_json_object(response, "sync.list_threads")
        items = [
            self.thread_brief(item)
            for item in self._as_objects(result.get("items"), "sync.list_threads.items")
        ]
        return {
            "channel_id": args.channel_id,
            "items": items,
            "total": result.get("total"),
            "limit": result.get("limit"),
            "offset": result.get("offset"),
        }

    async def get_thread(self, thread_id: str | SyncGetThreadArgs) -> JsonObject:
        if isinstance(thread_id, SyncGetThreadArgs):
            args = thread_id
        else:
            args = SyncGetThreadArgs(thread_id=thread_id)
        response = await self._http.get(
            "sync",
            f"{_API}/threads/{quote(args.thread_id, safe='')}",
        )
        result = require_json_object(response, "sync.get_thread")
        return self.thread_brief(result)

    async def create_thread(
        self,
        channel_id: str | SyncCreateThreadArgs,
        root_message_id: str = "",
        title: str | None = None,
    ) -> JsonObject:
        if isinstance(channel_id, SyncCreateThreadArgs):
            args = channel_id
        else:
            args = SyncCreateThreadArgs(
                channel_id=channel_id,
                root_message_id=root_message_id,
                title=title,
            )
        body: JsonObject = {"root_message_id": args.root_message_id}
        if args.title is not None:
            body["title"] = args.title
        response = await self._http.post(
            "sync",
            f"{_API}/threads/",
            params={"channel_id": args.channel_id},
            json=body,
        )
        result = require_json_object(response, "sync.create_thread")
        return self.thread_brief(result)

    async def list_thread_messages(
        self,
        channel_id: str | SyncListThreadMessagesArgs,
        thread_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> JsonObject:
        if isinstance(channel_id, SyncListThreadMessagesArgs):
            args = channel_id
        else:
            args = SyncListThreadMessagesArgs(
                channel_id=channel_id,
                thread_id=thread_id,
                limit=limit,
                offset=offset,
            )
        response = await self._http.get(
            "sync",
            (
                f"{_API}/channels/{quote(args.channel_id, safe='')}"
                f"/threads/{quote(args.thread_id, safe='')}/messages"
            ),
            params={"limit": str(args.limit), "offset": str(args.offset)},
        )
        result = require_json_object(response, "sync.list_thread_messages")
        items = [
            self.message_brief(item)
            for item in self._as_objects(result.get("items"), "sync.list_thread_messages.items")
        ]
        return {
            "channel_id": args.channel_id,
            "thread_id": args.thread_id,
            "count": len(items),
            "items": items,
            "total": result.get("total"),
            "limit": result.get("limit"),
            "offset": result.get("offset"),
        }
