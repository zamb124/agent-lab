"""
Идемпотентность OnlyOffice callback: Redis SET NX на короткий TTL.
"""

from __future__ import annotations

import hashlib

from core.clients.redis_client import RedisClient

KEY_PREFIX = "office:oo_cb:"
TTL_SECONDS = 300


def callback_dedupe_redis_key(binding_id: str, status: int, url: str) -> str:
    payload = f"{binding_id}\n{status}\n{url}".encode()
    digest = hashlib.sha256(payload).hexdigest()
    return f"{KEY_PREFIX}{digest}"


async def try_claim_onlyoffice_callback(
    redis_url: str,
    binding_id: str,
    status: int,
    url: str,
) -> bool:
    """
    Возвращает:
        True — первый приём, продолжать загрузку и запись в S3.
        False — дубликат callback, вернуть OnlyOffice error=0 без повторной записи.
    """
    if not redis_url or not redis_url.strip():
        raise ValueError("database.redis_url обязателен для OnlyOffice callback")
    key = callback_dedupe_redis_key(binding_id, status, url)
    client = RedisClient(redis_url)
    try:
        await client.connect()
        return await client.set_nx(key, "1", TTL_SECONDS)
    finally:
        await client.close()
