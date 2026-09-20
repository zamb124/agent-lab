"""Presence: онлайн через Centrifugo HTTP API bus; last_seen — Redis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.clients.redis_client import RedisClient
from core.realtime.presence import fetch_users_presence

SYNC_LAST_SEEN_PREFIX = "sync:last_seen:"
SYNC_LAST_SEEN_TTL_SEC = 365 * 24 * 3600


def sync_last_seen_key(user_id: str) -> str:
    return f"{SYNC_LAST_SEEN_PREFIX}{user_id}"


async def _with_redis(redis_url: str) -> RedisClient:
    client = RedisClient(redis_url)
    await client.connect()
    return client


@dataclass(frozen=True, slots=True)
class PeerPresenceRow:
    """Снимок присутствия одного пользователя для API /company/members."""

    user_id: str
    is_online: bool
    last_seen_at: str | None


async def batch_peer_presence(redis_url: str, user_ids: list[str]) -> dict[str, PeerPresenceRow]:
    """Онлайн — Centrifugo presence; last_seen — Redis, если офлайн."""
    if not user_ids:
        return {}
    batch = await fetch_users_presence(user_ids)
    by_id = {item.user_id: item for item in batch.items}
    client = await _with_redis(redis_url)
    try:
        out: dict[str, PeerPresenceRow] = {}
        for user_id in user_ids:
            snapshot = by_id.get(user_id)
            if snapshot is None:
                raise RuntimeError(f"presence batch missing user_id {user_id}")
            if snapshot.connected:
                _ = await client.set(
                    sync_last_seen_key(user_id),
                    datetime.now(timezone.utc).isoformat(),
                    ttl=SYNC_LAST_SEEN_TTL_SEC,
                )
                out[user_id] = PeerPresenceRow(user_id=user_id, is_online=True, last_seen_at=None)
                continue
            raw_last_seen = await client.get(sync_last_seen_key(user_id))
            out[user_id] = PeerPresenceRow(
                user_id=user_id,
                is_online=False,
                last_seen_at=raw_last_seen,
            )
        return out
    finally:
        await client.close()
