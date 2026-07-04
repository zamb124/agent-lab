"""Structured Redis inventory log events for Loki/Grafana."""

from __future__ import annotations

from core.logging import get_logger
from core.logging.attributes import (
    EVENT_REDIS_INVENTORY_DB_SUMMARY,
    EVENT_REDIS_INVENTORY_PREFIX_STATS,
    EVENT_REDIS_INVENTORY_STREAM_LENGTH,
    EVENT_REDIS_INVENTORY_TICK_COMPLETED,
    EVENT_REDIS_INVENTORY_TICK_FAILED,
    EVENT_REDIS_INVENTORY_TICK_STARTED,
    LOG_EXCEPTION_MESSAGE,
    LOG_EXCEPTION_TYPE,
    LOG_REDIS_DB,
    LOG_REDIS_DBSIZE,
    LOG_REDIS_INVENTORY_DURATION_MS,
    LOG_REDIS_KEYS_SCANNED,
    LOG_REDIS_MAXMEMORY_BYTES,
    LOG_REDIS_NO_TTL_TOTAL,
    LOG_REDIS_PLATFORM_SCHEDULES_COUNT,
    LOG_REDIS_PREFIX,
    LOG_REDIS_PREFIX_KEY_COUNT,
    LOG_REDIS_PREFIX_NO_TTL_COUNT,
    LOG_REDIS_PREFIX_SAMPLE_MEMORY_BYTES,
    LOG_REDIS_SCAN_MISMATCH,
    LOG_REDIS_STREAM_MAXLEN,
    LOG_REDIS_STREAM_NAME,
    LOG_REDIS_STREAM_XLEN,
    LOG_REDIS_URL_LABEL,
    LOG_REDIS_USED_MEMORY_BYTES,
)
from core.redis_inventory.models import RedisDbInventory, RedisInventoryResult

logger = get_logger("platform.redis_inventory")


def log_redis_inventory_tick_started() -> None:
    logger.info(EVENT_REDIS_INVENTORY_TICK_STARTED)


def log_redis_inventory_db_summary(inventory: RedisDbInventory) -> None:
    logger.info(
        EVENT_REDIS_INVENTORY_DB_SUMMARY,
        **{
            LOG_REDIS_DB: inventory.redis_db,
            LOG_REDIS_URL_LABEL: inventory.redis_url_label,
            LOG_REDIS_DBSIZE: inventory.dbsize,
            LOG_REDIS_USED_MEMORY_BYTES: inventory.used_memory_bytes,
            LOG_REDIS_MAXMEMORY_BYTES: inventory.maxmemory_bytes,
            LOG_REDIS_KEYS_SCANNED: inventory.keys_scanned,
            LOG_REDIS_NO_TTL_TOTAL: inventory.no_ttl_total,
            LOG_REDIS_SCAN_MISMATCH: inventory.scan_dbsize_mismatch,
            LOG_REDIS_PLATFORM_SCHEDULES_COUNT: inventory.platform_schedules_count,
        },
    )


def log_redis_inventory_stream_length(
    *,
    redis_db: int,
    stream_name: str,
    stream_xlen: int,
    stream_maxlen: int | None,
) -> None:
    stream_fields: dict[str, int | str | None] = {
        LOG_REDIS_DB: redis_db,
        LOG_REDIS_STREAM_NAME: stream_name,
        LOG_REDIS_STREAM_XLEN: stream_xlen,
        LOG_REDIS_STREAM_MAXLEN: stream_maxlen,
    }
    logger.info(EVENT_REDIS_INVENTORY_STREAM_LENGTH, **stream_fields)


def log_redis_inventory_prefix_stats(
    *,
    redis_db: int,
    prefix: str,
    prefix_key_count: int,
    prefix_no_ttl_count: int,
    prefix_sample_memory_bytes: int,
) -> None:
    logger.info(
        EVENT_REDIS_INVENTORY_PREFIX_STATS,
        **{
            LOG_REDIS_DB: redis_db,
            LOG_REDIS_PREFIX: prefix,
            LOG_REDIS_PREFIX_KEY_COUNT: prefix_key_count,
            LOG_REDIS_PREFIX_NO_TTL_COUNT: prefix_no_ttl_count,
            LOG_REDIS_PREFIX_SAMPLE_MEMORY_BYTES: prefix_sample_memory_bytes,
        },
    )


def log_redis_inventory_tick_completed(result: RedisInventoryResult) -> None:
    logger.info(
        EVENT_REDIS_INVENTORY_TICK_COMPLETED,
        **{
            LOG_REDIS_INVENTORY_DURATION_MS: result.duration_ms,
        },
    )


def log_redis_inventory_tick_failed(
    *,
    exception_type: str,
    exception_message: str,
) -> None:
    logger.error(
        EVENT_REDIS_INVENTORY_TICK_FAILED,
        **{
            LOG_EXCEPTION_TYPE: exception_type,
            LOG_EXCEPTION_MESSAGE: exception_message,
        },
    )
