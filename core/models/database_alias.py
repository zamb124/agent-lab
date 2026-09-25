"""Ленивое открытие пула Oxyde для алиаса модели.

Старт процесса поднимает свою базу, shared и tracing. Остальные алиасы
открываются здесь, когда запрос впервые к ним обращается.
"""

from __future__ import annotations

import asyncio

from oxyde import PoolSettings
from oxyde.db.pool import AsyncDatabase
from oxyde.db.registry import get_connection

from core.logging import get_logger

logger = get_logger(__name__)

_alias_urls: dict[str, str] = {}
_alias_locks: dict[str, asyncio.Lock] = {}
_max_connections = 0
_acquire_timeout = 0.0


def configure_oxyde_aliases(
    urls: dict[str, str],
    *,
    max_connections: int,
    acquire_timeout: float,
) -> None:
    """Запомнить URL алиасов и размер пула. Пустые URL не записываются."""
    global _max_connections, _acquire_timeout
    if max_connections < 1:
        raise RuntimeError("pool max_connections must be at least 1")
    if acquire_timeout <= 0:
        raise RuntimeError("pool acquire_timeout must be positive")
    _max_connections = max_connections
    _acquire_timeout = acquire_timeout
    for alias, url in urls.items():
        if alias == "" or url == "":
            raise RuntimeError(f"database alias {alias} has an empty URL")
        _alias_urls[alias] = url


async def ensure_oxyde_alias(alias: str | None) -> None:
    """Открыть пул алиаса, если старт процесса его не регистрировал."""
    if alias is None or alias == "" or alias == "default":
        return
    try:
        _ = await get_connection(alias)
    except KeyError:
        lock = _alias_locks.setdefault(alias, asyncio.Lock())
        async with lock:
            try:
                _ = await get_connection(alias)
            except KeyError:
                url = _alias_urls.get(alias)
                if url is None:
                    raise RuntimeError(f"database alias {alias} has no URL") from None
                pool = PoolSettings(
                    max_connections=_max_connections,
                    acquire_timeout=_acquire_timeout,
                )
                database = AsyncDatabase(
                    url,
                    name=alias,
                    settings=pool,
                    auto_register=True,
                    overwrite=True,
                )
                await database.connect()
                logger.info("oxyde.alias_ready", alias=alias)
