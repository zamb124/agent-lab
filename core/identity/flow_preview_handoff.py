"""Одноразовый handoff для гостевой страницы preview embed (Redis GETDEL)."""

from __future__ import annotations

import json

from core.clients.redis_client import RedisClient
from core.types import JsonObject, parse_json_object

_FLOW_PREVIEW_HANDOFF_PREFIX = "flow_preview_handoff:"


def flow_preview_handoff_redis_key(handoff_id: str) -> str:
    hid = handoff_id.strip()
    if not hid:
        raise ValueError("handoff_id must be non-empty")
    return f"{_FLOW_PREVIEW_HANDOFF_PREFIX}{hid}"


async def store_flow_preview_handoff(
    *,
    redis: RedisClient,
    handoff_id: str,
    payload: JsonObject,
    ttl_seconds: int,
) -> None:
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be positive")
    raw = json.dumps(payload, ensure_ascii=False)
    ok = await redis.setex(flow_preview_handoff_redis_key(handoff_id), ttl_seconds, raw)
    if not ok:
        raise RuntimeError("flow_preview_handoff: redis SETEX failed")


async def consume_flow_preview_handoff(
    *,
    redis: RedisClient,
    handoff_id: str,
) -> JsonObject | None:
    raw = await redis.getdel(flow_preview_handoff_redis_key(handoff_id))
    if raw is None or raw == "":
        return None
    return parse_json_object(raw, "flow_preview_handoff payload")


async def peek_flow_preview_handoff(*, redis: RedisClient, handoff_id: str) -> bool:
    raw = await redis.get(flow_preview_handoff_redis_key(handoff_id))
    return raw is not None and raw != ""
