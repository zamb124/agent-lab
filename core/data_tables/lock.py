"""Redis mutation lock на DataTable file_id."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from core.clients.redis_client import RedisClient

_LOCK_TTL_SECONDS = 120
_LOCK_FALLBACK_POLL_SECONDS = 2.0


class DataTableLockedError(ValueError):
    """Файл таблицы уже изменяется другим процессом."""


def data_table_lock_key(file_id: str) -> str:
    return f"data_table:{file_id}:mutation"


def data_table_lock_release_channel(file_id: str) -> str:
    return f"data_table:{file_id}:mutation:released"


@asynccontextmanager
async def data_table_mutation_lock(
    redis_client: RedisClient,
    file_id: str,
    *,
    wait_timeout_seconds: float = 45.0,
) -> AsyncGenerator[None, None]:
    lock_key = data_table_lock_key(file_id)
    release_channel = data_table_lock_release_channel(file_id)
    token = uuid.uuid4().hex
    deadline = asyncio.get_running_loop().time() + wait_timeout_seconds

    ok = await redis_client.set_nx(lock_key, token, _LOCK_TTL_SECONDS)
    if not ok:
        pubsub = await redis_client.open_pubsub()
        await pubsub.subscribe(release_channel)
        try:
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise DataTableLockedError(f"data table {file_id} is locked")
                _ = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=min(remaining, _LOCK_FALLBACK_POLL_SECONDS),
                )
                ok = await redis_client.set_nx(lock_key, token, _LOCK_TTL_SECONDS)
                if ok:
                    break
        finally:
            await pubsub.unsubscribe(release_channel)
            await pubsub.aclose()
    try:
        yield
    finally:
        _ = await redis_client.delete(lock_key)
        _ = await redis_client.publish(release_channel, "released")
