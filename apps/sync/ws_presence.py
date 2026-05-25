"""Redis: пользователь с активным WebSocket /sync/ws (для отложенных push без дубля с realtime)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, cast

from redis.asyncio.client import Redis

from core.config import get_settings

SYNC_WS_PRESENCE_PREFIX = "sync:ws:presence:"

SYNC_LAST_SEEN_PREFIX = "sync:last_seen:"
SYNC_LAST_SEEN_TTL_SEC = 365 * 24 * 3600


class _SyncPresencePipeline(Protocol):
    def exists(self, key: str) -> "_SyncPresencePipeline": ...

    def get(self, key: str) -> "_SyncPresencePipeline": ...

    def execute(self) -> Awaitable[list[int | str | bytes | None]]: ...


class _SyncPresenceRedis(Protocol):
    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
    ) -> Awaitable[bool | None]: ...

    def delete(self, name: str) -> Awaitable[int]: ...

    def get(self, name: str) -> Awaitable[str | bytes | None]: ...

    def pipeline(self) -> _SyncPresencePipeline: ...

    def aclose(self) -> Awaitable[None]: ...


def _presence_redis(redis_url: str) -> _SyncPresenceRedis:
    from_url = cast(Callable[[str], _SyncPresenceRedis], Redis.from_url)
    return from_url(redis_url)


def sync_ws_presence_key(user_id: str) -> str:
    return f"{SYNC_WS_PRESENCE_PREFIX}{user_id}"


def sync_last_seen_key(user_id: str) -> str:
    return f"{SYNC_LAST_SEEN_PREFIX}{user_id}"


async def refresh_sync_ws_presence(redis_url: str, user_id: str) -> None:
    ttl = get_settings().ws_presence_ttl_seconds
    r = _presence_redis(redis_url)
    try:
        _ = await r.set(sync_ws_presence_key(user_id), "1", ex=ttl)
    finally:
        await r.aclose()


async def clear_sync_ws_presence(redis_url: str, user_id: str) -> None:
    r = _presence_redis(redis_url)
    try:
        _ = await r.delete(sync_ws_presence_key(user_id))
    finally:
        await r.aclose()


async def is_user_sync_ws_online(redis_url: str, user_id: str) -> bool:
    r = _presence_redis(redis_url)
    try:
        v = await r.get(sync_ws_presence_key(user_id))
        return v is not None
    finally:
        await r.aclose()


async def set_last_seen_now(redis_url: str, user_id: str) -> str:
    now = datetime.now(timezone.utc)
    iso = now.isoformat()
    r = _presence_redis(redis_url)
    try:
        _ = await r.set(sync_last_seen_key(user_id), iso, ex=SYNC_LAST_SEEN_TTL_SEC)
        return iso
    finally:
        await r.aclose()


@dataclass(frozen=True, slots=True)
class PeerPresenceRow:
    """Снимок присутствия одного пользователя для API /company/members."""

    user_id: str
    is_online: bool
    last_seen_at: str | None


async def batch_peer_presence(redis_url: str, user_ids: list[str]) -> dict[str, PeerPresenceRow]:
    """По списку user_id: онлайн (ключ presence) и last_seen из Redis (если офлайн)."""
    if not user_ids:
        return {}
    r = _presence_redis(redis_url)
    try:
        pipe = r.pipeline()
        for uid in user_ids:
            _ = pipe.exists(sync_ws_presence_key(uid))
            _ = pipe.get(sync_last_seen_key(uid))
        raw = await pipe.execute()
    finally:
        await r.aclose()

    out: dict[str, PeerPresenceRow] = {}
    for i, uid in enumerate(user_ids):
        exists_val = raw[i * 2]
        get_val = raw[i * 2 + 1]
        online = bool(exists_val)
        last_seen: str | None
        if isinstance(get_val, bytes):
            last_seen = get_val.decode("utf-8")
        elif isinstance(get_val, str):
            last_seen = get_val
        else:
            last_seen = None
        if online:
            out[uid] = PeerPresenceRow(user_id=uid, is_online=True, last_seen_at=None)
        else:
            out[uid] = PeerPresenceRow(user_id=uid, is_online=False, last_seen_at=last_seen)
    return out
