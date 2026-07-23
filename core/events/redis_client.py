"""Redis-клиент процесса для шины `platform:events` (publish + catalog HASH)."""

from __future__ import annotations

from typing import Protocol, cast

from redis.asyncio.client import Redis

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


class _RedisFromUrl(Protocol):
    def __call__(self, url: str, *, decode_responses: bool) -> Redis: ...


_events_client: Redis | None = None


def events_redis_client() -> Redis:
    """Lazy Redis-клиент шины: один на процесс (HTTP и worker)."""
    global _events_client
    if _events_client is not None:
        return _events_client
    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise RuntimeError("database.redis_url is required for platform events")
    from_url = cast(_RedisFromUrl, Redis.from_url)
    _events_client = from_url(redis_url, decode_responses=True)
    logger.info("platform_events.redis_client_initialized")
    return _events_client


async def close_events_redis_client() -> None:
    """Закрыть Redis-клиент шины (shutdown / тесты)."""
    global _events_client
    client = _events_client
    _events_client = None
    if client is not None:
        await client.aclose()
