"""
Временное хранение текста импорта (inline из мастера) в Redis до забора воркером.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol
from typing import cast as type_cast

import redis.asyncio as redis_async

from core.config import get_settings

KEY_PREFIX = "crm:knowledge_import:text:"
TTL_SECONDS = 86400 * 7


class _KnowledgeImportRedis(Protocol):
    def setex(self, name: str, time: int, value: str) -> Awaitable[bool]: ...

    def get(self, name: str) -> Awaitable[str | None]: ...

    def delete(self, *names: str) -> Awaitable[int]: ...

    def aclose(self) -> Awaitable[None]: ...


class _RedisFromUrl(Protocol):
    def __call__(self, url: str, *, decode_responses: bool) -> _KnowledgeImportRedis: ...


def _key(import_id: str) -> str:
    return KEY_PREFIX + import_id


def _redis_client(redis_url: str) -> _KnowledgeImportRedis:
    redis_from_url = type_cast(_RedisFromUrl, redis_async.Redis.from_url)
    return redis_from_url(redis_url, decode_responses=True)


def _redis_url() -> str:
    url = get_settings().database.redis_url
    if not url:
        raise ValueError("database.redis_url не задан")
    return str(url)


async def store_pending_import_text(import_id: str, text: str) -> None:
    if not import_id or not import_id.strip():
        raise ValueError("import_id обязателен")
    client = _redis_client(_redis_url())
    try:
        ok = await client.setex(_key(import_id), TTL_SECONDS, text)
        if not ok:
            raise RuntimeError("Redis SETEX вернул ложь")
    finally:
        await client.aclose()


async def get_pending_import_text(import_id: str) -> str:
    client = _redis_client(_redis_url())
    try:
        raw = await client.get(_key(import_id))
    finally:
        await client.aclose()
    if raw is None:
        raise ValueError(f"Текст импорта в Redis не найден: {import_id}")
    return raw


async def delete_pending_import_text(import_id: str) -> None:
    client = _redis_client(_redis_url())
    try:
        _ = await client.delete(_key(import_id))
    finally:
        await client.aclose()
