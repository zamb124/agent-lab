"""Redis-клиент процесса для шины `platform:events` (publish + catalog HASH)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Protocol

from core.clients.redis_from_url import redis_client_from_url
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


class _EventsRedis(Protocol):
    def hset(self, name: str, *, mapping: dict[str, str]) -> Awaitable[int]: ...

    def hgetall(self, name: str) -> Awaitable[dict[str, str]]: ...

    def hdel(self, name: str, *keys: str) -> Awaitable[int]: ...

    def xadd(
        self,
        name: str,
        fields: dict[str, str],
        *,
        maxlen: int,
        approximate: bool,
    ) -> Awaitable[str | bytes]: ...

    def aclose(self) -> Awaitable[None]: ...


_events_client: _EventsRedis | None = None
_events_client_loop: asyncio.AbstractEventLoop | None = None


def events_redis_client() -> _EventsRedis:
    """Lazy Redis-клиент шины: один на текущий running event loop.

    Starlette ``TestClient`` поднимает отдельный loop на каждый ``with``-блок.
    Клиент, созданный на закрытом/чужом loop, даёт ``Event loop is closed`` /
    ``Future attached to a different loop`` на XADD/HSET — поэтому при смене
    loop синглтон пересоздаётся.
    """
    global _events_client, _events_client_loop
    loop = asyncio.get_running_loop()
    if _events_client is not None and _events_client_loop is loop:
        return _events_client
    if _events_client is not None:
        logger.warning(
            "platform_events.redis_client_loop_changed",
            previous_closed=_events_client_loop is None or _events_client_loop.is_closed(),
        )
        _events_client = None
        _events_client_loop = None
    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise RuntimeError("database.redis_url is required for platform events")
    _events_client = redis_client_from_url(_EventsRedis, redis_url, decode_responses=True)
    _events_client_loop = loop
    logger.info("platform_events.redis_client_initialized")
    return _events_client


async def close_events_redis_client() -> None:
    """Закрыть Redis-клиент шины (shutdown / тесты)."""
    global _events_client, _events_client_loop
    client = _events_client
    client_loop = _events_client_loop
    _events_client = None
    _events_client_loop = None
    if client is None:
        return
    running = asyncio.get_running_loop()
    if client_loop is not None and client_loop is not running:
        logger.warning("platform_events.redis_client_close_skipped_foreign_loop")
        return
    await client.aclose()
