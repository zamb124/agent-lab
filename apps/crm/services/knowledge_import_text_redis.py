"""
Временное хранение текста импорта (inline из мастера) в Redis до забора воркером.
"""

from __future__ import annotations

from core.clients.redis_client import RedisClient
from core.config import get_settings

KEY_PREFIX = "crm:knowledge_import:text:"
TTL_SECONDS = 86400 * 7


def _key(import_id: str) -> str:
    return KEY_PREFIX + import_id


def _redis_client() -> RedisClient:
    url = get_settings().database.redis_url
    if not url:
        raise ValueError("database.redis_url is not set")
    return RedisClient(url)


async def store_pending_import_text(import_id: str, text: str) -> None:
    if not import_id or not import_id.strip():
        raise ValueError("import_id is required")
    client = _redis_client()
    await client.connect()
    try:
        ok = await client.setex(_key(import_id), TTL_SECONDS, text)
        if not ok:
            raise RuntimeError("Redis SETEX returned false")
    finally:
        await client.close()


async def get_pending_import_text(import_id: str) -> str:
    client = _redis_client()
    await client.connect()
    try:
        raw = await client.get(_key(import_id))
    finally:
        await client.close()
    if raw is None:
        raise ValueError(f"Import text not found in Redis: {import_id}")
    return raw


async def delete_pending_import_text(import_id: str) -> None:
    client = _redis_client()
    await client.connect()
    try:
        _ = await client.delete(_key(import_id))
    finally:
        await client.close()
