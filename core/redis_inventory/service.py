"""Full Redis key/stream inventory for observability."""

from __future__ import annotations

import time
from collections import defaultdict
from urllib.parse import urlparse

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.events.contract import PLATFORM_EVENTS_STREAM
from core.redis_inventory.logging_events import (
    log_redis_inventory_db_summary,
    log_redis_inventory_prefix_stats,
    log_redis_inventory_stream_length,
    log_redis_inventory_tick_completed,
    log_redis_inventory_tick_started,
)
from core.redis_inventory.models import (
    RedisDbInventory,
    RedisInventoryResult,
    RedisPrefixStats,
    RedisStreamLength,
)
from core.tasks.broker import stream_maxlen_for_queue

TASKIQ_STREAM_NAMES: tuple[str, ...] = (
    "search",
    "idle",
    "crm",
    "rag",
    "flows_worker",
    "sync",
    "taskiq",
)

PREFIX_SAMPLE_LIMIT = 3
TTL_BATCH_SIZE = 200


def prefix_for_key(key: str) -> str:
    if ":" in key:
        parts = key.split(":")
        if len(parts) >= 3 and parts[0] == "flows" and parts[1] == "workflow_projection":
            return "flows:workflow_projection:"
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}:"
        return f"{parts[0]}:"
    return key


def _redis_db_index(redis_url: str) -> int:
    parsed = urlparse(redis_url)
    if not parsed.path or parsed.path == "/":
        return 0
    db_raw = parsed.path.lstrip("/")
    return int(db_raw)


async def _collect_prefix_stats(
    redis_client: RedisClient,
    keys: list[str],
) -> tuple[dict[str, RedisPrefixStats], int]:
    prefix_counts: dict[str, int] = defaultdict(int)
    prefix_no_ttl: dict[str, int] = defaultdict(int)
    prefix_memory: dict[str, int] = defaultdict(int)
    prefix_sampled: dict[str, int] = defaultdict(int)
    no_ttl_total = 0

    if not keys:
        return {}, 0

    for batch_start in range(0, len(keys), TTL_BATCH_SIZE):
        batch = keys[batch_start : batch_start + TTL_BATCH_SIZE]
        ttl_results = await redis_client.ttl_batch(batch)
        for key, ttl_seconds in zip(batch, ttl_results, strict=True):
            prefix = prefix_for_key(key)
            prefix_counts[prefix] += 1
            if ttl_seconds == -1:
                prefix_no_ttl[prefix] += 1
                no_ttl_total += 1
            if prefix_sampled[prefix] < PREFIX_SAMPLE_LIMIT:
                memory_bytes = await redis_client.memory_usage(key)
                if memory_bytes is not None:
                    prefix_memory[prefix] += memory_bytes
                prefix_sampled[prefix] += 1

    prefix_stats = {
        prefix: RedisPrefixStats(
            prefix=prefix,
            key_count=prefix_counts[prefix],
            no_ttl_count=prefix_no_ttl[prefix],
            sample_memory_bytes=prefix_memory[prefix],
        )
        for prefix in prefix_counts
    }
    return prefix_stats, no_ttl_total


async def _inventory_db(
    *,
    redis_client: RedisClient,
    redis_url: str,
    redis_url_label: str,
    include_streams: bool,
) -> RedisDbInventory:
    redis_db = _redis_db_index(redis_url)
    memory_info = await redis_client.info_memory()
    dbsize = await redis_client.dbsize()
    keys = await redis_client.scan_all_keys()
    prefix_stats_map, no_ttl_total = await _collect_prefix_stats(redis_client, keys)
    keys_scanned = len(keys)
    scan_dbsize_mismatch = keys_scanned != dbsize

    stream_lengths: tuple[RedisStreamLength, ...] = ()
    if include_streams:
        collected_streams: list[RedisStreamLength] = []
        for stream_name in TASKIQ_STREAM_NAMES:
            stream_xlen = await redis_client.xlen(stream_name)
            collected_streams.append(
                RedisStreamLength(
                    stream_name=stream_name,
                    stream_xlen=stream_xlen,
                    stream_maxlen=stream_maxlen_for_queue(stream_name),
                )
            )
        platform_events_xlen = await redis_client.xlen(PLATFORM_EVENTS_STREAM)
        collected_streams.append(
            RedisStreamLength(
                stream_name=PLATFORM_EVENTS_STREAM,
                stream_xlen=platform_events_xlen,
                stream_maxlen=get_settings().events.stream_maxlen,
            )
        )
        stream_lengths = tuple(collected_streams)

    platform_schedule_keys = await redis_client.scan_keys("platform_schedules*")
    platform_schedules_count = len(platform_schedule_keys)

    ranked_prefixes = sorted(
        prefix_stats_map.values(),
        key=lambda stats: stats.sample_memory_bytes,
        reverse=True,
    )

    return RedisDbInventory(
        redis_db=redis_db,
        redis_url_label=redis_url_label,
        dbsize=dbsize,
        used_memory_bytes=memory_info.used_memory_bytes,
        maxmemory_bytes=memory_info.maxmemory_bytes,
        keys_scanned=keys_scanned,
        no_ttl_total=no_ttl_total,
        scan_dbsize_mismatch=scan_dbsize_mismatch,
        prefix_stats=tuple(ranked_prefixes),
        stream_lengths=stream_lengths,
        platform_schedules_count=platform_schedules_count,
    )


def _emit_db_inventory(inventory: RedisDbInventory) -> None:
    log_redis_inventory_db_summary(inventory)
    for stream_length in inventory.stream_lengths:
        log_redis_inventory_stream_length(
            redis_db=inventory.redis_db,
            stream_name=stream_length.stream_name,
            stream_xlen=stream_length.stream_xlen,
            stream_maxlen=stream_length.stream_maxlen,
        )
    for prefix_stats in inventory.prefix_stats:
        log_redis_inventory_prefix_stats(
            redis_db=inventory.redis_db,
            prefix=prefix_stats.prefix,
            prefix_key_count=prefix_stats.key_count,
            prefix_no_ttl_count=prefix_stats.no_ttl_count,
            prefix_sample_memory_bytes=prefix_stats.sample_memory_bytes,
        )


async def run_redis_inventory_tick() -> RedisInventoryResult:
    settings = get_settings()
    domain_url = settings.database.redis_url
    broker_url = settings.tasks.broker_url
    if not domain_url:
        raise ValueError("database.redis_url is required for redis_inventory_tick")
    if not broker_url:
        raise ValueError("tasks.broker_url is required for redis_inventory_tick")

    log_redis_inventory_tick_started()
    started_at = time.monotonic()

    domain_redis = RedisClient(domain_url)
    broker_redis = RedisClient(broker_url)
    await domain_redis.connect()
    await broker_redis.connect()
    try:
        domain_inventory = await _inventory_db(
            redis_client=domain_redis,
            redis_url=domain_url,
            redis_url_label="DATABASE__REDIS_URL",
            include_streams=False,
        )
        broker_inventory = await _inventory_db(
            redis_client=broker_redis,
            redis_url=broker_url,
            redis_url_label="TASKS__BROKER_URL",
            include_streams=True,
        )
    finally:
        await domain_redis.close()
        await broker_redis.close()

    _emit_db_inventory(domain_inventory)
    _emit_db_inventory(broker_inventory)

    duration_ms = (time.monotonic() - started_at) * 1000.0
    result = RedisInventoryResult(
        domain_db=domain_inventory,
        broker_db=broker_inventory,
        duration_ms=duration_ms,
    )
    log_redis_inventory_tick_completed(result)
    return result
