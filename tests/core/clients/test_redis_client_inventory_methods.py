"""Tests for RedisClient inventory read methods."""

from __future__ import annotations

import pytest

from apps.flows.config import get_settings
from core.clients.redis_client import RedisClient, RedisMemoryInfo


@pytest.fixture
async def redis_client() -> RedisClient:
    settings = get_settings()
    client = RedisClient(settings.database.redis_url)
    await client.connect()
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_dbsize_and_scan_all_keys(redis_client: RedisClient, unique_id: str) -> None:
    key = f"inventory_test:{unique_id}:dbsize"
    await redis_client.set(key, "value", ttl=60)

    dbsize_before = await redis_client.dbsize()
    keys = await redis_client.scan_all_keys()
    assert key in keys
    assert dbsize_before >= 1

    await redis_client.delete(key)


@pytest.mark.asyncio
async def test_ttl_and_memory_usage(redis_client: RedisClient, unique_id: str) -> None:
    ttl_key = f"inventory_test:{unique_id}:ttl"

    await redis_client.set(ttl_key, "with_ttl", ttl=120)

    ttl_seconds = await redis_client.ttl(ttl_key)
    assert ttl_seconds > 0

    memory_bytes = await redis_client.memory_usage(ttl_key)
    assert memory_bytes is not None
    assert memory_bytes > 0

    await redis_client.delete(ttl_key)


@pytest.mark.asyncio
async def test_xlen_stream(redis_client: RedisClient, unique_id: str) -> None:
    stream_name = f"inventory_stream:{unique_id}"
    length = await redis_client.xlen(stream_name)
    assert length == 0


@pytest.mark.asyncio
async def test_info_memory(redis_client: RedisClient) -> None:
    memory_info = await redis_client.info_memory()
    assert isinstance(memory_info, RedisMemoryInfo)
    assert memory_info.used_memory_bytes > 0
    assert memory_info.used_memory_rss_bytes > 0
