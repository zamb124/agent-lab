"""Redis-backed provider availability state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from core.clients.redis_client import RedisClient, RedisOperationError


class ProviderAvailabilityRecord(BaseModel):
    """Last known provider availability snapshot."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider_id: str = Field(..., min_length=1)
    available: bool
    checked_at: str = Field(..., min_length=1)
    consecutive_failures: int = Field(default=0, ge=0)
    last_error: str | None = None


class ProviderAvailabilityStore:
    """Strict Redis store for search provider availability."""

    _redis: RedisClient
    _key_prefix: str
    _available_ttl_seconds: int
    _unavailable_ttl_seconds: int

    def __init__(
        self,
        redis_client: RedisClient,
        *,
        key_prefix: str,
        available_ttl_seconds: int,
        unavailable_ttl_seconds: int,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix.rstrip(":")
        self._available_ttl_seconds = available_ttl_seconds
        self._unavailable_ttl_seconds = unavailable_ttl_seconds

    async def get(self, provider_id: str) -> ProviderAvailabilityRecord | None:
        raw = await self._redis.eval(
            "return redis.call('GET', KEYS[1])",
            1,
            self._key(provider_id),
        )
        if raw is None:
            return None
        if not isinstance(raw, str):  # pragma: no cover - Redis GET returns only string or nil.
            raise RedisOperationError(
                f"search provider availability record is not a string: {provider_id}"
            )
        return ProviderAvailabilityRecord.model_validate_json(raw)

    async def mark_available(self, provider_id: str) -> ProviderAvailabilityRecord:
        record = ProviderAvailabilityRecord(
            provider_id=provider_id,
            available=True,
            checked_at=self._now(),
            consecutive_failures=0,
        )
        await self._set(record, ttl_seconds=self._available_ttl_seconds)
        return record

    async def mark_unavailable(self, provider_id: str, error: str) -> ProviderAvailabilityRecord:
        existing = await self.get(provider_id)
        consecutive_failures = 1
        if existing is not None:
            consecutive_failures = existing.consecutive_failures + 1
        record = ProviderAvailabilityRecord(
            provider_id=provider_id,
            available=False,
            checked_at=self._now(),
            consecutive_failures=consecutive_failures,
            last_error=error[:500],
        )
        await self._set(record, ttl_seconds=self._unavailable_ttl_seconds)
        return record

    async def clear(self, provider_id: str) -> None:
        _ = await self._redis.delete(self._key(provider_id))

    def _key(self, provider_id: str) -> str:
        return f"{self._key_prefix}:{provider_id}"

    async def _set(self, record: ProviderAvailabilityRecord, *, ttl_seconds: int) -> None:
        ok = await self._redis.set(
            self._key(record.provider_id),
            record.model_dump_json(),
            ttl=ttl_seconds,
        )
        if not ok:  # pragma: no cover - strict guard for Redis write failure.
            raise RedisOperationError(
                f"search provider availability write failed: {record.provider_id}"
            )

    def _now(self) -> str:
        return datetime.now(tz=UTC).isoformat()
