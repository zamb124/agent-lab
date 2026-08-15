"""Tests for Redis inventory service."""

from __future__ import annotations

import pytest

from apps.flows.config import get_settings
from core.clients.redis_client import RedisClient
from core.redis_inventory.service import _inventory_db, prefix_for_key


@pytest.mark.parametrize(
    ("key", "expected_prefix"),
    [
        ("flows:workflow_projection:company:session", "flows:workflow_projection:"),
        ("platform_schedules:data:abc", "platform_schedules:data:"),
        ("search", "search"),
        ("crm:foo:bar", "crm:foo:"),
    ],
)
def test_prefix_for_key(key: str, expected_prefix: str) -> None:
    assert prefix_for_key(key) == expected_prefix


@pytest.mark.asyncio
async def test_inventory_db_domain(unique_id: str) -> None:
    settings = get_settings()
    domain_redis = RedisClient(settings.database.redis_url)
    await domain_redis.connect()
    probe_key = f"inventory_tick:{unique_id}"
    try:
        await domain_redis.set(probe_key, "probe", ttl=120)
        inventory = await _inventory_db(
            redis_client=domain_redis,
            redis_url=settings.database.redis_url,
            redis_url_label="DATABASE__REDIS_URL",
            include_streams=False,
        )
    finally:
        await domain_redis.delete(probe_key)
        await domain_redis.close()

    assert inventory.redis_url_label == "DATABASE__REDIS_URL"
    assert inventory.dbsize >= 1
    assert inventory.keys_scanned >= 1
    assert inventory.used_memory_bytes > 0
    # DBSIZE и SCAN — два снимка: при параллельной записи они расходятся,
    # это штатный сигнал inventory.scan_dbsize_mismatch, не ошибка SCAN.
    assert inventory.scan_dbsize_mismatch is (inventory.keys_scanned != inventory.dbsize)
    tick_prefix = prefix_for_key(probe_key)
    tick_stats = next(
        (stats for stats in inventory.prefix_stats if stats.prefix == tick_prefix),
        None,
    )
    assert tick_stats is not None
    assert tick_stats.key_count >= 1
