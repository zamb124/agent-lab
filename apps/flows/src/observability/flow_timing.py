"""Product SLI: latency от enqueue flow task до первого content chunk."""

from __future__ import annotations

import time

from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_FLOW_FIRST_CONTENT_CHUNK,
    EVENT_FLOW_TASK_ENQUEUED,
    EVENT_FLOW_TERMINAL,
    LOG_FLOW_FIRST_CHUNK_MS,
    LOG_FLOW_ID,
    LOG_FLOW_TERMINAL_MS,
    LOG_FLOW_TERMINAL_STATE,
    LOG_TASK_ID,
)

_logger = get_logger(__name__)

_FLOW_ENQUEUE_TS_PREFIX = "flow_enqueue_ts:"
_FLOW_ENQUEUE_TS_TTL_SECONDS = 3600


def _enqueue_key(task_id: str) -> str:
    if task_id == "":
        raise ValueError("task_id обязателен для flow timing")
    return f"{_FLOW_ENQUEUE_TS_PREFIX}{task_id}"


async def record_flow_task_enqueued(
    redis_client: RedisClient,
    *,
    task_id: str,
    flow_id: str,
) -> None:
    enqueued_at = time.time()
    key = _enqueue_key(task_id)
    stored = await redis_client.set(key, str(enqueued_at), ttl=_FLOW_ENQUEUE_TS_TTL_SECONDS)
    if not stored:
        raise RuntimeError(f"Не удалось записать flow enqueue timestamp: task_id={task_id!r}")
    _logger.info(
        EVENT_FLOW_TASK_ENQUEUED,
        **{
            LOG_TASK_ID: task_id,
            LOG_FLOW_ID: flow_id,
            "flow_task_enqueued_at": enqueued_at,
        },
    )


async def maybe_record_flow_first_content_chunk(
    redis_client: RedisClient,
    *,
    task_id: str,
    flow_id: str,
    text: str,
) -> None:
    if text == "":
        return
    key = _enqueue_key(task_id)
    raw_enqueued_at = await redis_client.get(key)
    if raw_enqueued_at is None:
        return
    try:
        enqueued_at = float(raw_enqueued_at)
    except ValueError as exc:
        raise ValueError(f"Некорректный flow enqueue timestamp для task_id={task_id!r}") from exc
    first_chunk_ms = round((time.time() - enqueued_at) * 1000.0, 3)
    _logger.info(
        EVENT_FLOW_FIRST_CONTENT_CHUNK,
        **{
            LOG_TASK_ID: task_id,
            LOG_FLOW_ID: flow_id,
            LOG_FLOW_FIRST_CHUNK_MS: first_chunk_ms,
        },
    )


async def maybe_record_flow_terminal(
    redis_client: RedisClient,
    *,
    task_id: str,
    flow_id: str,
    terminal_state: str,
) -> None:
    if terminal_state == "":
        raise ValueError("terminal_state обязателен для flow terminal timing")
    key = _enqueue_key(task_id)
    raw_enqueued_at = await redis_client.getdel(key)
    if raw_enqueued_at is None:
        return
    try:
        enqueued_at = float(raw_enqueued_at)
    except ValueError as exc:
        raise ValueError(f"Некорректный flow enqueue timestamp для task_id={task_id!r}") from exc
    terminal_ms = round((time.time() - enqueued_at) * 1000.0, 3)
    _logger.info(
        EVENT_FLOW_TERMINAL,
        **{
            LOG_TASK_ID: task_id,
            LOG_FLOW_ID: flow_id,
            LOG_FLOW_TERMINAL_MS: terminal_ms,
            LOG_FLOW_TERMINAL_STATE: terminal_state,
        },
    )
