"""Typed models for Redis inventory snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedisPrefixStats:
    prefix: str
    key_count: int
    no_ttl_count: int
    sample_memory_bytes: int


@dataclass(frozen=True)
class RedisStreamLength:
    stream_name: str
    stream_xlen: int
    stream_maxlen: int | None


@dataclass(frozen=True)
class RedisDbInventory:
    redis_db: int
    redis_url_label: str
    dbsize: int
    used_memory_bytes: int
    maxmemory_bytes: int | None
    keys_scanned: int
    no_ttl_total: int
    scan_dbsize_mismatch: bool
    prefix_stats: tuple[RedisPrefixStats, ...]
    stream_lengths: tuple[RedisStreamLength, ...]
    platform_schedules_count: int


@dataclass(frozen=True)
class RedisInventoryResult:
    domain_db: RedisDbInventory
    broker_db: RedisDbInventory
    duration_ms: float
