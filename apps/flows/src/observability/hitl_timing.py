"""Product SLI: HITL interrupt → operator response (resume)."""

from __future__ import annotations

import time

from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_HITL_OPERATOR_RESPONDED,
    LOG_FLOW_ID,
    LOG_HITL_QUEUE_SLUG,
    LOG_HITL_WAIT_MS,
    LOG_HITL_WORK_ITEM_ID,
    LOG_TASK_ID,
)

_logger = get_logger(__name__)

_HITL_INTERRUPT_TS_PREFIX = "hitl_interrupt_ts:"
_HITL_INTERRUPT_TS_TTL_SECONDS = 604800


def _hitl_key(work_item_id: str) -> str:
    if work_item_id == "":
        raise ValueError("work_item_id обязателен для HITL timing")
    return f"{_HITL_INTERRUPT_TS_PREFIX}{work_item_id}"


async def record_hitl_interrupt(
    redis_client: RedisClient,
    *,
    work_item_id: str,
) -> None:
    interrupted_at = time.time()
    key = _hitl_key(work_item_id)
    stored = await redis_client.set(
        key,
        str(interrupted_at),
        ttl=_HITL_INTERRUPT_TS_TTL_SECONDS,
    )
    if not stored:
        raise RuntimeError(
            f"Не удалось записать HITL interrupt timestamp: work_item_id={work_item_id!r}"
        )


async def maybe_record_hitl_operator_response(
    redis_client: RedisClient,
    *,
    work_item_id: str,
    queue_slug: str,
    task_id: str,
    flow_id: str,
) -> None:
    key = _hitl_key(work_item_id)
    raw_interrupted_at = await redis_client.getdel(key)
    if raw_interrupted_at is None:
        return
    try:
        interrupted_at = float(raw_interrupted_at)
    except ValueError as exc:
        raise ValueError(
            f"Некорректный HITL interrupt timestamp: work_item_id={work_item_id!r}"
        ) from exc
    wait_ms = round((time.time() - interrupted_at) * 1000.0, 3)
    _logger.info(
        EVENT_HITL_OPERATOR_RESPONDED,
        **{
            LOG_HITL_WAIT_MS: wait_ms,
            LOG_HITL_WORK_ITEM_ID: work_item_id,
            LOG_HITL_QUEUE_SLUG: queue_slug,
            LOG_TASK_ID: task_id,
            LOG_FLOW_ID: flow_id,
        },
    )
