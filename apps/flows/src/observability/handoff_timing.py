"""Product SLI: wall time agent handoff initiated → handback completed."""

from __future__ import annotations

import time

from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_HANDOFF_WALL_TIME,
    LOG_FLOW_ID,
    LOG_HANDOFF_DEPTH,
    LOG_HANDOFF_TARGET_FLOW_ID,
    LOG_HANDOFF_WALL_MS,
)

_logger = get_logger(__name__)

_HANDOFF_INITIATED_TS_PREFIX = "handoff_initiated_ts:"
_HANDOFF_INITIATED_TS_TTL_SECONDS = 86400


def _handoff_key(child_session_id: str) -> str:
    if child_session_id == "":
        raise ValueError("child_session_id is required for handoff timing")
    return f"{_HANDOFF_INITIATED_TS_PREFIX}{child_session_id}"


async def record_handoff_initiated(
    redis_client: RedisClient,
    *,
    child_session_id: str,
) -> None:
    initiated_at = time.time()
    key = _handoff_key(child_session_id)
    stored = await redis_client.set(
        key,
        str(initiated_at),
        ttl=_HANDOFF_INITIATED_TS_TTL_SECONDS,
    )
    if not stored:
        raise RuntimeError(
            f"Failed to write handoff initiated timestamp: child_session_id={child_session_id!r}"
        )


async def maybe_record_handoff_wall_time(
    redis_client: RedisClient,
    *,
    child_session_id: str,
    target_flow_id: str,
    depth: int,
) -> None:
    key = _handoff_key(child_session_id)
    raw_initiated_at = await redis_client.getdel(key)
    if raw_initiated_at is None:
        return
    try:
        initiated_at = float(raw_initiated_at)
    except ValueError as exc:
        raise ValueError(
            f"Invalid handoff initiated timestamp: child_session_id={child_session_id!r}"
        ) from exc
    wall_ms = round((time.time() - initiated_at) * 1000.0, 3)
    _logger.info(
        EVENT_HANDOFF_WALL_TIME,
        **{
            LOG_HANDOFF_WALL_MS: wall_ms,
            LOG_HANDOFF_TARGET_FLOW_ID: target_flow_id,
            LOG_HANDOFF_DEPTH: depth,
            LOG_FLOW_ID: child_session_id.split(":", 1)[0],
        },
    )
