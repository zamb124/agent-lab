"""Redis: пользователь с активным WebSocket /sync/ws (для отложенных push без дубля с realtime)."""

from __future__ import annotations

import redis.asyncio as redis

SYNC_WS_PRESENCE_PREFIX = "sync:ws:presence:"
SYNC_WS_PRESENCE_TTL_SEC = 120


def sync_ws_presence_key(user_id: str) -> str:
    return f"{SYNC_WS_PRESENCE_PREFIX}{user_id}"


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
