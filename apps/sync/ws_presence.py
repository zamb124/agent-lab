"""Redis: пользователь с активным WebSocket /sync/ws (для отложенных push без дубля с realtime)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.clients.redis_client import RedisClient
from core.config import get_settings

SYNC_WS_PRESENCE_PREFIX = "sync:ws:presence:"

SYNC_LAST_SEEN_PREFIX = "sync:last_seen:"
SYNC_LAST_SEEN_TTL_SEC = 365 * 24 * 3600


def sync_ws_presence_key(user_id: str) -> str:
    return f"{SYNC_WS_PRESENCE_PREFIX}{user_id}"


def sync_last_seen_key(user_id: str) -> str:
    return f"{SYNC_LAST_SEEN_PREFIX}{user_id}"


async def _with_redis(redis_url: str) -> RedisClient:
    client = RedisClient(redis_url)
    await client.connect()
    return client


async def refresh_sync_ws_presence(redis_url: str, user_id: str) -> None:
    ttl = get_settings().ws_presence_ttl_seconds
    client = await _with_redis(redis_url)
    try:
        _ = await client.set(sync_ws_presence_key(user_id), "1", ttl=ttl)
    finally:
        await client.close()


async def clear_sync_ws_presence(redis_url: str, user_id: str) -> None:
    client = await _with_redis(redis_url)
    try:
        _ = await client.delete(sync_ws_presence_key(user_id))
    finally:
        await client.close()


async def is_user_sync_ws_online(redis_url: str, user_id: str) -> bool:
    client = await _with_redis(redis_url)
    try:
        exists_count = await client.exists(sync_ws_presence_key(user_id))
        return exists_count > 0
    finally:
        await client.close()


async def set_last_seen_now(redis_url: str, user_id: str) -> str:
    now = datetime.now(timezone.utc)
    iso = now.isoformat()
    client = await _with_redis(redis_url)
    try:
        _ = await client.set(sync_last_seen_key(user_id), iso, ttl=SYNC_LAST_SEEN_TTL_SEC)
        return iso
    finally:
        await client.close()


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
    client = await _with_redis(redis_url)
    try:
        out: dict[str, PeerPresenceRow] = {}
        for uid in user_ids:
            online = await client.exists(sync_ws_presence_key(uid)) > 0
            if online:
                out[uid] = PeerPresenceRow(user_id=uid, is_online=True, last_seen_at=None)
                continue
            raw_last_seen = await client.get(sync_last_seen_key(uid))
            out[uid] = PeerPresenceRow(
                user_id=uid,
                is_online=False,
                last_seen_at=raw_last_seen,
            )
        return out
    finally:
        await client.close()
