"""Redis lock: at most one crawl LLM enrichment in-flight on GPU."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as redis_async

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

CRAWL_ENRICHMENT_LOCK_KEY = "crawl:enrichment:gpu"
LOCK_TTL_SECONDS = 600
LOCK_WAIT_INITIAL_MS = 200
LOCK_WAIT_MAX_MS = 5000
LOCK_WAIT_TIMEOUT_SECONDS = 900


@asynccontextmanager
async def crawl_enrichment_lock() -> AsyncGenerator[None]:
    settings = get_settings()
    redis_client = redis_async.from_url(settings.database.redis_url, decode_responses=True)
    delay_ms = LOCK_WAIT_INITIAL_MS
    total_waited = 0.0
    acquired = False
    try:
        while total_waited < LOCK_WAIT_TIMEOUT_SECONDS:
            acquired = bool(
                await redis_client.set(
                    CRAWL_ENRICHMENT_LOCK_KEY,
                    "locked",
                    nx=True,
                    ex=LOCK_TTL_SECONDS,
                )
            )
            if acquired:
                logger.debug("crawl enrichment lock acquired")
                yield
                return
            await asyncio.sleep(delay_ms / 1000)
            total_waited += delay_ms / 1000
            delay_ms = min(delay_ms * 2, LOCK_WAIT_MAX_MS)
        raise TimeoutError(
            f"crawl enrichment lock wait exceeded {LOCK_WAIT_TIMEOUT_SECONDS}s"
        )
    finally:
        if acquired:
            _ = await redis_client.delete(CRAWL_ENRICHMENT_LOCK_KEY)
            logger.debug("crawl enrichment lock released")
        await redis_client.aclose()
