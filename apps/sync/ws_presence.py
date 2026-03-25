"""Redis: пользователь с активным WebSocket /sync/ws (для отложенных push без дубля с realtime)."""

from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as redis

SYNC_WS_PRESENCE_PREFIX = "sync:ws:presence:"
SYNC_WS_PRESENCE_TTL_SEC = 120

SYNC_LAST_SEEN_PREFIX = "sync:last_seen:"
SYNC_LAST_SEEN_TTL_SEC = 365 * 24 * 3600


def sync_ws_presence_key(user_id: str) -> str:
    return f"{SYNC_WS_PRESENCE_PREFIX}{user_id}"


def sync_last_seen_key(user_id: str) -> str:
    return f"{SYNC_LAST_SEEN_PREFIX}{user_id}"


async def refresh_sync_ws_presence(redis_url: str, user_id: str) -> None:
    r = redis.from_url(redis_url)
    try:
        await r.set(sync_ws_presence_key(user_id), "1", ex=SYNC_WS_PRESENCE_TTL_SEC)
    finally:
        await r.aclose()


async def clear_sync_ws_presence(redis_url: str, user_id: str) -> None:
    r = redis.from_url(redis_url)
    try:
        await r.delete(sync_ws_presence_key(user_id))
    finally:
        await r.aclose()


async def is_user_sync_ws_online(redis_url: str, user_id: str) -> bool:
    r = redis.from_url(redis_url)
    try:
        v = await r.get(sync_ws_presence_key(user_id))
        return v is not None
    finally:
        await r.aclose()


async def set_last_seen_now(redis_url: str, user_id: str) -> str:
    now = datetime.now(timezone.utc)
    iso = now.isoformat()
    r = redis.from_url(redis_url)
    try:
        await r.set(sync_last_seen_key(user_id), iso, ex=SYNC_LAST_SEEN_TTL_SEC)
        return iso
    finally:
        await r.aclose()


class PeerPresenceRow:
    """Снимок присутствия одного пользователя для API /company/members."""

    __slots__ = ("user_id", "is_online", "last_seen_at")

    def __init__(self, user_id: str, is_online: bool, last_seen_at: str | None) -> None:
        self.user_id = user_id
        self.is_online = is_online
        self.last_seen_at = last_seen_at


async def batch_peer_presence(redis_url: str, user_ids: list[str]) -> dict[str, PeerPresenceRow]:
    """По списку user_id: онлайн (ключ presence) и last_seen из Redis (если офлайн)."""
    if not user_ids:
        return {}
    r = redis.from_url(redis_url)
    try:
        pipe = r.pipeline()
        for uid in user_ids:
            pipe.exists(sync_ws_presence_key(uid))
            pipe.get(sync_last_seen_key(uid))
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
