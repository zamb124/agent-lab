"""
Временное хранение текста импорта (inline из мастера) в Redis до забора воркером.
"""

from __future__ import annotations

import redis.asyncio as redis_async

from core.config import get_settings

KEY_PREFIX = "crm:knowledge_import:text:"
TTL_SECONDS = 86400 * 7


def _key(import_id: str) -> str:
    return KEY_PREFIX + import_id


async def store_pending_import_text(import_id: str, text: str) -> None:
    if not import_id or not import_id.strip():
        raise ValueError("import_id обязателен")
    if text is None:
        raise ValueError("text не может быть None")
    settings = get_settings()
    url = settings.database.redis_url
    if not url:
        raise ValueError("database.redis_url не задан")
    client = redis_async.from_url(str(url), decode_responses=True)
    try:
        ok = await client.setex(_key(import_id), TTL_SECONDS, text)
        if not ok:
            raise RuntimeError("Redis SETEX вернул ложь")
    finally:
        await client.aclose()


async def get_pending_import_text(import_id: str) -> str:
    settings = get_settings()
    url = settings.database.redis_url
    if not url:
        raise ValueError("database.redis_url не задан")
    client = redis_async.from_url(str(url), decode_responses=True)
    try:
        raw = await client.get(_key(import_id))
    finally:
        await client.aclose()
    if raw is None:
        raise ValueError(f"Текст импорта в Redis не найден: {import_id}")
    return raw


async def delete_pending_import_text(import_id: str) -> None:
    settings = get_settings()
    url = settings.database.redis_url
    if not url:
        raise ValueError("database.redis_url не задан")
    client = redis_async.from_url(str(url), decode_responses=True)
    try:
        await client.delete(_key(import_id))
    finally:
        await client.aclose()
