"""Live Centrifugo RPC + REST identity для всех SYNC_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /sync/api/internal/realtime/command` → тот же `op_*`.
REST — Granian :9005, префикс `/sync/api/v1`.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from httpx2 import AsyncClient, Response

from apps.sync.realtime.command_router import SYNC_OPERATIONS
from core.di.platform import PlatformDi
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    platform_auxiliary_upload_spec_json,
)
from tests.fixtures.audio_bytes import minimal_wav_silence
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event
from tests.sync.api._helpers import seed_namespace_via_repo

_API = "/sync/api/v1"
_COMPANY_ID = "system"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"-(?:ws|rest)(?=$|\W)")
_VOLATILE_KEYS = frozenset(
    {
        "channel_id",
        "thread_id",
        "message_id",
        "root_message_id",
        "parent_message_id",
        "call_id",
        "link_token",
        "git_ref_id",
        "project_key",
        "external_id",
        "file_id",
        "recording_id",
        "provider_job_id",
        "token",
        "username",
        "credential",
        "ttl",
        "livekit_token",
        "livekit_url",
        "livekit_room_name",
        "participant_identity",
        "join_url",
        "request_id",
        "trace_id",
        "service",
        "observability",
        "detail",
        "created_at",
        "updated_at",
        "sent_at",
        "edited_at",
        "started_at",
        "ended_at",
        "expires_at",
        "joined_at",
        "left_at",
        "last_seen_at",
        "last_message_at",
        "scheduled_start_at",
        "scheduled_end_at",
        "url",
        "avatar_url",
        "creator_avatar_url",
        "is_online",
        "unread_count",
        "mention_unread_count",
        "last_message_preview",
        "namespace",
        "name",
        "pinned_message_ids",
    }
)

CompareMode = Literal["normalized", "marker_row"]
PayloadStrategy = Literal["body", "body_minus_path", "body_field", "query", "none"]
ExpectMode = Literal["succeeded", "failed"]
SetupFn = Callable[["LiveCtx"], Awaitable[JsonObject]]


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy
    query_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn
    same_resource: bool
    compare: CompareMode
    expect: ExpectMode = "succeeded"
    marker_field: str = "name"


@dataclass
class LiveCtx:
    client: AsyncClient
    headers: dict[str, str]
    headers_user2: dict[str, str]
    unique_id: str
    suffix: str
    system_user2_id: str
    di: PlatformDi
    marker: str | None = None


def _json(response: Response, label: str) -> JsonObject:
    return require_json_object(response.json(), label)


def _str_field(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{key} is required, got {value!r}")
    return value


def _token(ctx: LiveCtx) -> str:
    return f"-{ctx.suffix}-{ctx.unique_id}"


def _strip_transport_marker(text: str) -> str:
    return _TRANSPORT_MARKER.sub("", text)


def _normalize(value: JsonValue | None) -> JsonValue | None:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _strip_transport_marker(text=value)
    return value


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    if response.status_code == 204:
        return {}
    return _json(response, label)


def _text_body(text: str) -> JsonObject:
    return {
        "thread_id": None,
        "parent_message_id": None,
        "contents": [{"type": "text/plain", "order": 0, "data": {"body": text}}],
    }


async def _namespace(ctx: LiveCtx) -> str:
    return await seed_namespace_via_repo(ctx.di, _COMPANY_ID, f"ns_{ctx.unique_id}_{ctx.suffix}")


async def _create_topic(
    ctx: LiveCtx,
    *,
    title: str | None = None,
    member_user_id: str | None = None,
) -> str:
    namespace = await _namespace(ctx)
    name = title if title is not None else f"Ch{_token(ctx)}"
    created = await ctx.client.post(
        f"{_API}/channels/",
        headers=ctx.headers,
        json={
            "type": "topic",
            "name": name,
            "namespace": namespace,
            "is_private": False,
        },
    )
    body = await _expect_json(created, ok=(201,), label="create channel")
    channel_id = _str_field(body, "channel_id")
    if member_user_id is not None:
        added = await ctx.client.post(
            f"{_API}/channels/{channel_id}/members",
            headers=ctx.headers,
            json={"user_id": member_user_id, "role": "member"},
        )
        _ = await _expect_json(added, ok=(201,), label="add member")
    return channel_id


async def _send_text(ctx: LiveCtx, channel_id: str, text: str) -> JsonObject:
    sent = await ctx.client.post(
        f"{_API}/channels/{channel_id}/messages",
        headers=ctx.headers,
        json=_text_body(text),
    )
    return await _expect_json(sent, ok=(201,), label="send text")


async def _create_thread(ctx: LiveCtx, root_message_id: str) -> JsonObject:
    created = await ctx.client.post(
        f"{_API}/threads/",
        headers=ctx.headers,
        json={"root_message_id": root_message_id},
    )
    return await _expect_json(created, ok=(201,), label="create thread")


async def _invite_call(ctx: LiveCtx, channel_id: str) -> JsonObject:
    invited = await ctx.client.post(
        f"{_API}/calls/any/invite",
        headers=ctx.headers,
        json={"channel_id": channel_id},
    )
    return await _expect_json(invited, ok=(200, 201), label="invite call")


async def _create_link(ctx: LiveCtx, channel_id: str) -> JsonObject:
    created = await ctx.client.post(
        f"{_API}/calls/links",
        headers=ctx.headers,
        json={"channel_id": channel_id, "call_type": "video", "ttl_hours": 24},
    )
    return await _expect_json(created, ok=(201,), label="create call link")


async def _setup_channels_list(ctx: LiveCtx) -> JsonObject:
    namespace = await _namespace(ctx)
    ctx.marker = f"List{_token(ctx)}"
    created = await ctx.client.post(
        f"{_API}/channels/",
        headers=ctx.headers,
        json={
            "type": "topic",
            "name": ctx.marker,
            "namespace": namespace,
            "is_private": False,
        },
    )
    _ = await _expect_json(created, ok=(201,), label="seed list channel")
    return {"namespace": namespace, "limit": 50, "offset": 0}


async def _setup_channels_create(ctx: LiveCtx) -> JsonObject:
    namespace = await _namespace(ctx)
    return {
        "type": "topic",
        "name": f"New{_token(ctx)}",
        "namespace": namespace,
        "is_private": False,
    }


async def _setup_channels_update(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    return {"channel_id": channel_id, "body": {"name": f"Ren{_token(ctx)}"}}


async def _setup_channel_id(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    return {"channel_id": channel_id}


async def _setup_channels_mark_read(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    _ = await _send_text(ctx, channel_id, f"read{_token(ctx)}")
    return {"channel_id": channel_id}


async def _setup_channels_typing(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    return {"channel_id": channel_id, "typing": True, "thread_id": None}


async def _setup_channels_notify(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    return {"channel_id": channel_id, "notifications_muted": True}


async def _setup_channels_add_member(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    return {"channel_id": channel_id, "user_id": ctx.system_user2_id, "role": "member"}


async def _setup_shared_channels(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx, member_user_id=ctx.system_user2_id)
    _ = channel_id
    return {"peer_user_id": ctx.system_user2_id, "limit": 50, "offset": 0}


async def _setup_company_members(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"limit": 50, "offset": 0}


async def _setup_threads_create(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    sent = await _send_text(ctx, channel_id, f"root{_token(ctx)}")
    return {"body": {"root_message_id": _str_field(sent, "message_id")}}


async def _setup_threads_list(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    sent = await _send_text(ctx, channel_id, f"root{_token(ctx)}")
    _ = await _create_thread(ctx, _str_field(sent, "message_id"))
    return {"channel_id": channel_id, "limit": 50, "offset": 0}


async def _setup_threads_item(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    sent = await _send_text(ctx, channel_id, f"root{_token(ctx)}")
    thread = await _create_thread(ctx, _str_field(sent, "message_id"))
    return {"thread_id": _str_field(thread, "thread_id")}


async def _setup_messages_send(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    return {"channel_id": channel_id, "body": _text_body(f"send{_token(ctx)}")}


async def _setup_messages_edit(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    sent = await _send_text(ctx, channel_id, f"before{_token(ctx)}")
    return {
        "channel_id": channel_id,
        "message_id": _str_field(sent, "message_id"),
        "body": {
            "contents": [
                {"type": "text/plain", "order": 0, "data": {"body": f"after{_token(ctx)}"}},
            ]
        },
    }


async def _setup_message_ids(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    sent = await _send_text(ctx, channel_id, f"msg{_token(ctx)}")
    return {"channel_id": channel_id, "message_id": _str_field(sent, "message_id")}


async def _setup_messages_forward(ctx: LiveCtx) -> JsonObject:
    from_id = await _create_topic(ctx, title=f"From{_token(ctx)}")
    to_id = await _create_topic(ctx, title=f"To{_token(ctx)}")
    sent = await _send_text(ctx, from_id, f"fwd{_token(ctx)}")
    return {
        "from_channel_id": from_id,
        "message_id": _str_field(sent, "message_id"),
        "to_channel_id": to_id,
        "thread_id": None,
    }


async def _setup_messages_react(ctx: LiveCtx) -> JsonObject:
    ids = await _setup_message_ids(ctx)
    return {**ids, "emoji": "👍"}


async def _setup_messages_pin(ctx: LiveCtx) -> JsonObject:
    ids = await _setup_message_ids(ctx)
    return {**ids, "action": "add"}


async def _setup_messages_list(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    _ = await _send_text(ctx, channel_id, f"listed{_token(ctx)}")
    return {"channel_id": channel_id, "limit": 20, "before": None, "after": None}


async def _setup_messages_list_thread(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    sent = await _send_text(ctx, channel_id, f"root{_token(ctx)}")
    thread = await _create_thread(ctx, _str_field(sent, "message_id"))
    return {
        "channel_id": channel_id,
        "thread_id": _str_field(thread, "thread_id"),
        "limit": 50,
        "offset": 0,
    }


async def _setup_git_upsert(ctx: LiveCtx) -> JsonObject:
    key = f"org{_token(ctx)}"
    return {
        "body": {
            "provider": "github",
            "kind": "repo",
            "project_key": key,
            "external_id": key,
            "url": f"https://github.com/{key}",
        }
    }


async def _setup_git_get(ctx: LiveCtx) -> JsonObject:
    key = f"get{_token(ctx)}"
    created = await ctx.client.post(
        f"{_API}/git/resources",
        headers=ctx.headers,
        json={
            "provider": "github",
            "kind": "repo",
            "project_key": key,
            "external_id": key,
            "url": f"https://github.com/{key}",
        },
    )
    body = await _expect_json(created, ok=(201,), label="git upsert")
    return {"git_ref_id": _str_field(body, "git_ref_id")}


async def _setup_turn(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {}


async def _setup_invite(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx, member_user_id=ctx.system_user2_id)
    return {"channel_id": channel_id}


async def _setup_invite_then_call(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx, member_user_id=ctx.system_user2_id)
    call = await _invite_call(ctx, channel_id)
    return {"call_id": _str_field(call, "call_id")}


async def _setup_solo_invite_call(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    call = await _invite_call(ctx, channel_id)
    return {"call_id": _str_field(call, "call_id")}


async def _setup_recording_stop(ctx: LiveCtx) -> JsonObject:
    call_payload = await _setup_solo_invite_call(ctx)
    call_id = _str_field(call_payload, "call_id")
    started = await ctx.client.post(
        f"{_API}/calls/{call_id}/recording/start",
        headers=ctx.headers,
    )
    _ = await _expect_json(started, ok=(200, 201), label="recording start")
    return {"call_id": call_id}


async def _setup_admin_transfer(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx, member_user_id=ctx.system_user2_id)
    call = await _invite_call(ctx, channel_id)
    call_id = _str_field(call, "call_id")
    accepted = await ctx.client.post(
        f"{_API}/calls/{call_id}/accept",
        headers=ctx.headers_user2,
    )
    _ = await _expect_json(accepted, ok=(200,), label="user2 accept")
    return {"call_id": call_id, "target_user_id": ctx.system_user2_id}


async def _setup_signal(ctx: LiveCtx) -> JsonObject:
    call_payload = await _setup_invite_then_call(ctx)
    return {
        "call_id": _str_field(call_payload, "call_id"),
        "target_user_id": ctx.system_user2_id,
        "signal_type": "offer",
        "data": {"sdp": "live-identity"},
    }


async def _setup_links_create(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    return {"channel_id": channel_id, "call_type": "video", "ttl_hours": 24}


async def _setup_links_list(ctx: LiveCtx) -> JsonObject:
    now = datetime.now(UTC)
    return {
        "start_at": (now - timedelta(days=1)).isoformat(),
        "end_at": (now + timedelta(days=7)).isoformat(),
        "limit": 50,
        "offset": 0,
    }


async def _setup_calendar_link(ctx: LiveCtx) -> JsonObject:
    now = datetime.now(UTC)
    created = await ctx.client.post(
        f"{_API}/calls/links",
        headers=ctx.headers,
        json={
            "calendar_event_id": f"cal{_token(ctx)}",
            "scheduled_title": f"Meet{_token(ctx)}",
            "scheduled_start_at": (now + timedelta(hours=1)).isoformat(),
            "scheduled_end_at": (now + timedelta(hours=2)).isoformat(),
            "calendar_member_user_ids": [],
        },
    )
    return await _expect_json(created, ok=(201,), label="calendar link")


async def _setup_links_update(ctx: LiveCtx) -> JsonObject:
    link = await _setup_calendar_link(ctx)
    return {
        "link_token": _str_field(link, "link_token"),
        "body": {"scheduled_title": f"Upd{_token(ctx)}"},
    }


async def _setup_links_remove(ctx: LiveCtx) -> JsonObject:
    link = await _setup_calendar_link(ctx)
    return {"link_token": _str_field(link, "link_token")}


async def _setup_join(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    link = await _create_link(ctx, channel_id)
    return {"link_token": _str_field(link, "link_token"), "body": None}


async def _setup_upload_completed(ctx: LiveCtx) -> JsonObject:
    uploaded = await chunked_upload_file(
        ctx.client,
        ctx.headers,
        content=b"sync live identity",
        original_name=f"note{_token(ctx)}.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(),
        files_api_prefix=f"{_API}/files",
    )
    body = await _expect_json(uploaded, ok=(200,), label="chunked upload")
    return {"file_id": _str_field(body, "file_id")}


async def _setup_transcribe_audio(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    uploaded = await chunked_upload_file(
        ctx.client,
        ctx.headers,
        content=minimal_wav_silence(duration_sec=0.05),
        original_name=f"note{_token(ctx)}.wav",
        content_type="audio/wav",
        spec_json=platform_auxiliary_upload_spec_json(),
        files_api_prefix=f"{_API}/files",
    )
    file_body = await _expect_json(uploaded, ok=(200,), label="audio upload")
    sent = await ctx.client.post(
        f"{_API}/channels/{channel_id}/messages",
        headers=ctx.headers,
        json={
            "thread_id": None,
            "parent_message_id": None,
            "contents": [
                {
                    "type": "file/audio",
                    "order": 0,
                    "data": {
                        "file_id": _str_field(file_body, "file_id"),
                        "original_name": "note.wav",
                        "content_type": "audio/wav",
                        "file_size": file_body["file_size"],
                        "duration_ms": 50,
                    },
                }
            ],
        },
    )
    message = await _expect_json(sent, ok=(201,), label="send audio")
    return {"channel_id": channel_id, "message_id": _str_field(message, "message_id")}


async def _setup_transcribe_video(ctx: LiveCtx) -> JsonObject:
    return await _setup_message_ids(ctx)


async def _setup_transcribe_call(ctx: LiveCtx) -> JsonObject:
    channel_id = await _create_topic(ctx)
    call = await _invite_call(ctx, channel_id)
    return {"channel_id": channel_id, "call_id": _str_field(call, "call_id")}


def _op(
    method: str,
    url: str,
    strategy: PayloadStrategy,
    setup: SetupFn,
    *,
    same: bool,
    compare: CompareMode = "normalized",
    expect: ExpectMode = "succeeded",
    marker_field: str = "name",
) -> OpCase:
    return OpCase(
        rest=RestMirror(method=method, url=url, strategy=strategy),
        setup=setup,
        same_resource=same,
        compare=compare,
        expect=expect,
        marker_field=marker_field,
    )


async def _setup_namespaces_list(ctx: LiveCtx) -> JsonObject:
    ctx.marker = await seed_namespace_via_repo(ctx.di, _COMPANY_ID, f"0ns_{ctx.unique_id}_{ctx.suffix}")
    return {"limit": 200, "offset": 0}


async def _setup_namespaces_update(ctx: LiveCtx) -> JsonObject:
    namespace = await _namespace(ctx)
    return {
        "name": namespace,
        "sync_settings": {"transcribe_voice_messages": True, "speech_to_chat_enabled": False},
    }


_CASES: dict[str, OpCase] = {
    "sync/channels/list_requested": _op(
        "GET", f"{_API}/channels/", "query", _setup_channels_list,
        same=True, compare="marker_row",
    ),
    "sync/namespaces/list_requested": _op(
        "GET", f"{_API}/namespaces", "query", _setup_namespaces_list,
        same=True, compare="marker_row",
    ),
    "sync/namespace/sync_settings_update_requested": _op(
        "PUT", f"{_API}/namespaces/{{name}}", "body_minus_path", _setup_namespaces_update,
        same=True,
    ),
    "sync/channels/create_requested": _op(
        "POST", f"{_API}/channels/", "body", _setup_channels_create, same=False,
    ),
    "sync/channels/update_requested": _op(
        "PATCH", f"{_API}/channels/{{channel_id}}", "body_field", _setup_channels_update, same=True,
    ),
    "sync/channels/mark_read_requested": _op(
        "POST", f"{_API}/channels/{{channel_id}}/read", "none", _setup_channels_mark_read, same=True,
    ),
    "sync/channels/typing_requested": _op(
        "POST", f"{_API}/channels/{{channel_id}}/typing", "body", _setup_channels_typing, same=True,
    ),
    "sync/channels/notification_settings_update_requested": _op(
        "PATCH",
        f"{_API}/channels/{{channel_id}}/notification-settings",
        "body_minus_path",
        _setup_channels_notify,
        same=True,
    ),
    "sync/channels/add_member_requested": _op(
        "POST",
        f"{_API}/channels/{{channel_id}}/members",
        "body_minus_path",
        _setup_channels_add_member,
        same=False,
    ),
    "sync/channels/list_members_requested": _op(
        "GET", f"{_API}/channels/{{channel_id}}/members", "none", _setup_channel_id, same=True,
    ),
    "sync/threads/list_requested": _op(
        "GET", f"{_API}/threads/", "query", _setup_threads_list, same=True,
    ),
    "sync/threads/create_requested": _op(
        "POST", f"{_API}/threads/", "body_field", _setup_threads_create, same=False,
    ),
    "sync/threads/item_requested": _op(
        "GET", f"{_API}/threads/{{thread_id}}", "none", _setup_threads_item, same=True,
    ),
    "sync/messages/list_requested": _op(
        "GET", f"{_API}/channels/{{channel_id}}/messages", "query", _setup_messages_list, same=True,
    ),
    "sync/messages/list_thread_requested": _op(
        "GET",
        f"{_API}/channels/{{channel_id}}/threads/{{thread_id}}/messages",
        "query",
        _setup_messages_list_thread,
        same=True,
    ),
    "sync/messages/send_requested": _op(
        "POST",
        f"{_API}/channels/{{channel_id}}/messages",
        "body_field",
        _setup_messages_send,
        same=False,
    ),
    "sync/messages/edit_requested": _op(
        "PATCH",
        f"{_API}/channels/{{channel_id}}/messages/{{message_id}}",
        "body_field",
        _setup_messages_edit,
        same=True,
    ),
    "sync/messages/delete_requested": _op(
        "DELETE",
        f"{_API}/channels/{{channel_id}}/messages/{{message_id}}",
        "none",
        _setup_message_ids,
        same=False,
    ),
    "sync/messages/forward_requested": _op(
        "POST",
        f"{_API}/channels/{{channel_id}}/messages/{{message_id}}/forward",
        "body",
        _setup_messages_forward,
        same=False,
    ),
    "sync/messages/react_requested": _op(
        "POST",
        f"{_API}/channels/{{channel_id}}/messages/{{message_id}}/react",
        "body",
        _setup_messages_react,
        same=True,
    ),
    "sync/messages/pin_requested": _op(
        "POST", f"{_API}/channels/{{channel_id}}/pins", "body", _setup_messages_pin, same=True,
    ),
    "sync/messages/mark_read_requested": _op(
        "POST",
        f"{_API}/channels/{{channel_id}}/messages/{{message_id}}/read",
        "none",
        _setup_message_ids,
        same=True,
    ),
    "sync/messages/transcribe_audio_requested": _op(
        "POST",
        f"{_API}/channels/{{channel_id}}/messages/{{message_id}}/transcribe",
        "none",
        _setup_transcribe_audio,
        same=True,
    ),
    "sync/messages/transcribe_video_requested": _op(
        "POST",
        f"{_API}/channels/{{channel_id}}/messages/{{message_id}}/transcribe-video",
        "none",
        _setup_transcribe_video,
        same=True,
        expect="failed",
    ),
    "sync/messages/transcribe_call_requested": _op(
        "POST",
        f"{_API}/channels/{{channel_id}}/calls/{{call_id}}/transcribe",
        "none",
        _setup_transcribe_call,
        same=True,
    ),
    "sync/git_resources/upsert_requested": _op(
        "POST", f"{_API}/git/resources", "body_field", _setup_git_upsert, same=False,
    ),
    "sync/git_resources/get_requested": _op(
        "GET", f"{_API}/git/resources/{{git_ref_id}}", "none", _setup_git_get, same=True,
    ),
    "sync/calls/invite_requested": _op(
        "POST", f"{_API}/calls/any/invite", "body", _setup_invite, same=False,
    ),
    "sync/calls/accept_requested": _op(
        "POST", f"{_API}/calls/{{call_id}}/accept", "none", _setup_invite_then_call, same=True,
    ),
    "sync/calls/decline_requested": _op(
        "POST", f"{_API}/calls/{{call_id}}/decline", "none", _setup_invite_then_call, same=True,
    ),
    "sync/calls/hangup_requested": _op(
        "POST", f"{_API}/calls/{{call_id}}/hangup", "none", _setup_invite_then_call, same=False,
    ),
    "sync/calls/recording_start_requested": _op(
        "POST",
        f"{_API}/calls/{{call_id}}/recording/start",
        "none",
        _setup_solo_invite_call,
        same=False,
    ),
    "sync/calls/recording_stop_requested": _op(
        "POST",
        f"{_API}/calls/{{call_id}}/recording/stop",
        "none",
        _setup_recording_stop,
        same=False,
    ),
    "sync/calls/admin_transfer_requested": _op(
        "POST",
        f"{_API}/calls/{{call_id}}/admin/transfer",
        "body",
        _setup_admin_transfer,
        same=False,
    ),
    "sync/calls/signal_requested": _op(
        "POST", f"{_API}/calls/{{call_id}}/signal", "body", _setup_signal, same=True,
    ),
    "sync/calls/get_requested": _op(
        "GET", f"{_API}/calls/{{call_id}}", "none", _setup_invite_then_call, same=True,
    ),
    "sync/calls/recordings_list_requested": _op(
        "GET",
        f"{_API}/calls/{{call_id}}/recordings",
        "none",
        _setup_invite_then_call,
        same=True,
    ),
    "sync/calls/token_requested": _op(
        "GET", f"{_API}/calls/{{call_id}}/token", "none", _setup_invite_then_call, same=True,
    ),
    "sync/calls/turn_credentials_requested": _op(
        "GET", f"{_API}/calls/turn-credentials", "none", _setup_turn, same=True,
    ),
    "sync/calls/links_list_requested": _op(
        "GET", f"{_API}/calls/links/scheduled", "query", _setup_links_list, same=True,
    ),
    "sync/calls/links_create_requested": _op(
        "POST", f"{_API}/calls/links", "body", _setup_links_create, same=False,
    ),
    "sync/calls/links_update_requested": _op(
        "PATCH",
        f"{_API}/calls/links/{{link_token}}",
        "body_field",
        _setup_links_update,
        same=True,
    ),
    "sync/calls/links_remove_requested": _op(
        "DELETE", f"{_API}/calls/links/{{link_token}}", "none", _setup_links_remove, same=False,
    ),
    "sync/calls/join_info_requested": _op(
        "GET", f"{_API}/calls/join/{{link_token}}", "none", _setup_join, same=True,
    ),
    "sync/calls/join_accept_requested": _op(
        "POST", f"{_API}/calls/join/{{link_token}}", "none", _setup_join, same=False,
    ),
    "sync/company_members/list_requested": _op(
        "GET", f"{_API}/company/members", "query", _setup_company_members, same=True,
    ),
    "sync/shared_channels/list_requested": _op(
        "GET",
        f"{_API}/company/members/{{peer_user_id}}/shared-channels",
        "query",
        _setup_shared_channels,
        same=True,
    ),
    "sync/files/upload_completed_requested": _op(
        "POST", f"{_API}/files/upload-completed", "body", _setup_upload_completed, same=True,
    ),
}


async def _ws_command(
    *,
    auth_token: str,
    realtime_session_client: AsyncClient,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 25.0,
) -> JsonObject:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("SESSION JWT is required")
    event_id = uuid.uuid4().hex
    succeeded = canonical_type[: -len("_requested")] + "_succeeded"
    failed = canonical_type[: -len("_requested")] + "_failed"
    async with connect_centrifugo(auth_token) as ws:
        accepted = await rpc_platform_event(
            ws,
            event_type=canonical_type,
            payload=payload,
            company_id=token_data.company_id,
            event_id=event_id,
        )
        assert accepted.get("accepted") is True
        assert accepted.get("event_id") == event_id
        deadline = asyncio.get_running_loop().time() + timeout_sec
        terminal_ws: JsonObject | None = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            event = await ws.recv_platform_event(timeout=remaining)
            event_type = event.get("type")
            if event_type not in (succeeded, failed):
                continue
            meta = event.get("meta")
            if not isinstance(meta, dict) or meta.get("causation_id") != event_id:
                continue
            terminal_ws = event
            break
    if terminal_ws is None:
        raise AssertionError(f"WS reply для {canonical_type!r} event_id={event_id} не получен")
    stored = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
    assert stored.status_code == 200, stored.text
    assert stored.json()["type"] == canonical_type
    terminal_http = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}/terminal")
    assert terminal_http.status_code == 200, terminal_http.text
    terminal = require_json_object(terminal_http.json(), "terminal")
    assert terminal["type"] == terminal_ws["type"]
    assert terminal["meta"]["causation_id"] == event_id
    return terminal_ws


def _query_params(payload: JsonObject, path_params: dict[str, str]) -> dict[str, JsonValue]:
    query: dict[str, JsonValue] = {}
    for key, value in payload.items():
        if key in path_params or value is None:
            continue
        query[key] = value
    return query


async def _rest_command(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    rest: RestMirror,
    payload: JsonObject,
    expect: ExpectMode,
) -> JsonObject:
    path_params: dict[str, str] = {}
    for key in _PATH_PLACEHOLDER.findall(rest.url):
        if key == "channel_id" and payload.get("channel_id") is None:
            path_params[key] = _str_field(payload, "from_channel_id")
            continue
        path_params[key] = _str_field(payload, key)
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    query_keys = set(rest.query_keys)
    if rest.strategy == "body":
        json_body = {k: v for k, v in payload.items() if k != "origin"}
    elif rest.strategy == "body_minus_path":
        body = {
            k: v
            for k, v in payload.items()
            if k not in path_params and k not in query_keys and k != "origin" and v is not None
        }
        json_body = body if body else None
    elif rest.strategy == "body_field":
        nested = payload.get("body")
        if not isinstance(nested, dict):
            raise AssertionError("body_field requires payload.body object")
        json_body = require_json_object(nested, "payload.body")
    elif rest.strategy == "query":
        query = _query_params(payload, path_params)
    elif rest.strategy == "none":
        pass
    else:
        raise AssertionError(f"unknown REST strategy {rest.strategy!r}")
    response = await client.request(
        rest.method,
        url,
        headers=headers,
        json=json_body,
        params=query,
    )
    if expect == "failed":
        return await _expect_json(
            response,
            ok=(400, 403, 404, 409, 422),
            label=f"REST {rest.method} {url}",
        )
    return await _expect_json(
        response,
        ok=(200, 201, 202, 204),
        label=f"REST {rest.method} {url}",
    )


def _row_by_marker(payload: JsonObject, field: str, marker: str) -> JsonObject:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("list payload must have items[]")
    matched: list[JsonObject] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get(field) == marker:
            matched.append(require_json_object(item, "list.row"))
    if len(matched) != 1:
        raise AssertionError(f"expected one row {field}={marker!r}, got {len(matched)}")
    return matched[0]


def test_every_sync_operation_has_live_case() -> None:
    missing = sorted(set(SYNC_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(SYNC_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(90)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_sync_op_ws_rest_identical(
    canonical_type: str,
    sync_service: None,
    sync_worker: None,
    realtime_service: None,
    sync_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_headers_system_user2: dict[str, str],
    auth_token_system: str,
    system_user2_id: str,
    unique_id: str,
    frontend_di,
) -> None:
    _ = sync_service, sync_worker, realtime_service
    headers = {**auth_headers_system, "Accept-Language": "ru"}
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(
        client=sync_client_http,
        headers=headers,
        headers_user2=auth_headers_system_user2,
        unique_id=unique_id,
        suffix="ws",
        system_user2_id=system_user2_id,
        di=frontend_di,
    )
    ws_payload = await case.setup(ws_ctx)
    ws_event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type=canonical_type,
        payload=ws_payload,
    )
    if case.expect == "succeeded":
        assert str(ws_event["type"]).endswith("_succeeded"), (
            f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
        )
    else:
        assert str(ws_event["type"]).endswith("_failed"), (
            f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
        )
    ws_result = _event_payload(ws_event)
    if case.same_resource:
        rest_payload = ws_payload
        rest_marker = ws_ctx.marker
    else:
        rest_ctx = LiveCtx(
            client=sync_client_http,
            headers=headers,
            headers_user2=auth_headers_system_user2,
            unique_id=unique_id,
            suffix="rest",
            system_user2_id=system_user2_id,
        di=frontend_di,
        )
        rest_payload = await case.setup(rest_ctx)
        rest_marker = rest_ctx.marker
    rest_result = await _rest_command(
        client=sync_client_http,
        headers=headers,
        rest=case.rest,
        payload=rest_payload,
        expect=case.expect,
    )
    if case.compare == "marker_row":
        if rest_marker is None:
            raise AssertionError("marker_row compare requires marker")
        assert _normalize(_row_by_marker(ws_result, case.marker_field, rest_marker)) == _normalize(
            _row_by_marker(rest_result, case.marker_field, rest_marker)
        ), f"WS != REST row для {canonical_type}"
        return
    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )
