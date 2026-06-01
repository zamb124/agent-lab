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

    async def get(self, provider_id: str, *, scope_id: str = "platform") -> ProviderAvailabilityRecord | None:
        raw = await self._redis.eval(
            "return redis.call('GET', KEYS[1])",
            1,
            self._key(scope_id, provider_id),
        )
        if raw is None:
            return None
        if not isinstance(raw, str):  # pragma: no cover - Redis GET returns only string or nil.
            raise RedisOperationError(
                f"search provider availability record is not a string: {provider_id}"
            )
        return ProviderAvailabilityRecord.model_validate_json(raw)

    async def mark_available(
        self,
        provider_id: str,
        *,
        scope_id: str = "platform",
    ) -> ProviderAvailabilityRecord:
        record = ProviderAvailabilityRecord(
            provider_id=provider_id,
            available=True,
            checked_at=self._now(),
            consecutive_failures=0,
        )
        await self._set(scope_id, record, ttl_seconds=self._available_ttl_seconds)
        return record

    async def mark_unavailable(
        self,
        provider_id: str,
        error: str,
        *,
        scope_id: str = "platform",
    ) -> ProviderAvailabilityRecord:
        existing = await self.get(provider_id, scope_id=scope_id)
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
        await self._set(scope_id, record, ttl_seconds=self._unavailable_ttl_seconds)
        return record

    async def clear(self, provider_id: str, *, scope_id: str = "platform") -> None:
        _ = await self._redis.delete(self._key(scope_id, provider_id))

    def _key(self, scope_id: str, provider_id: str) -> str:
        clean_scope = scope_id.strip().replace(":", "_")
        if not clean_scope:
            raise ValueError("provider availability scope_id is required")
        return f"{self._key_prefix}:{clean_scope}:{provider_id}"

    async def _set(
        self,
        scope_id: str,
        record: ProviderAvailabilityRecord,
        *,
        ttl_seconds: int,
    ) -> None:
        ok = await self._redis.set(
            self._key(scope_id, record.provider_id),
            record.model_dump_json(),
            ttl=ttl_seconds,
        )
        if not ok:  # pragma: no cover - strict guard for Redis write failure.
            raise RedisOperationError(
                f"search provider availability write failed: {record.provider_id}"
            )

    def _now(self) -> str:
        return datetime.now(tz=UTC).isoformat()
