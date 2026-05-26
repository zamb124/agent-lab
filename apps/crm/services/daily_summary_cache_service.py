"""
Кэш и state для daily summary в Redis.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Protocol
from typing import cast as type_cast

import redis.asyncio as redis_async

from core.types import JsonObject, parse_json_object


class _DailySummaryRedis(Protocol):
    def get(self, name: str) -> Awaitable[str | None]: ...

    def set(self, name: str, value: str, *, ex: int, nx: bool = False) -> Awaitable[bool | None]: ...

    def exists(self, *names: str) -> Awaitable[int]: ...

    def delete(self, *names: str) -> Awaitable[int]: ...


class _RedisFromUrl(Protocol):
    def __call__(self, url: str, *, decode_responses: bool) -> _DailySummaryRedis: ...


def _redis_client(redis_url: str) -> _DailySummaryRedis:
    redis_from_url = type_cast(_RedisFromUrl, redis_async.Redis.from_url)
    return redis_from_url(redis_url, decode_responses=True)


class DailySummaryCacheService:
    """Хранит состояние daily summary и lock в Redis."""

    def __init__(self, redis_url: str) -> None:
        self._redis: _DailySummaryRedis = _redis_client(redis_url)

    @staticmethod
    def _normalize_namespace(namespace: str | None) -> str:
        if namespace is None:
            return "all"
        if namespace.strip() == "":
            return "all"
        return namespace

    @classmethod
    def _state_key(cls, company_id: str, namespace: str | None, date_str: str) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        return f"crm:daily_summary:v1:{company_id}:{normalized_namespace}:{date_str}:state"

    @classmethod
    def _lock_key(cls, company_id: str, namespace: str | None, date_str: str) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        return f"crm:daily_summary:v1:{company_id}:{normalized_namespace}:{date_str}:lock"

    @classmethod
    def _revalidating_key(cls, company_id: str, namespace: str | None, date_str: str) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        return f"crm:daily_summary:v1:{company_id}:{normalized_namespace}:{date_str}:revalidating"

    async def get_state(
        self, company_id: str, namespace: str | None, date_str: str
    ) -> JsonObject | None:
        key = self._state_key(company_id=company_id, namespace=namespace, date_str=date_str)
        raw_value = await self._redis.get(key)
        if raw_value is None:
            return None
        return parse_json_object(raw_value, "daily_summary.redis_state")

    async def set_state(
        self,
        company_id: str,
        namespace: str | None,
        date_str: str,
        state: JsonObject,
        ttl_seconds: int = 60 * 60 * 24 * 7,
    ) -> None:
        key = self._state_key(company_id=company_id, namespace=namespace, date_str=date_str)
        ok = await self._redis.set(key, json.dumps(state, ensure_ascii=False), ex=ttl_seconds)
        if ok is not True:
            raise RuntimeError("Redis SET daily summary state returned false")

    async def is_revalidating(self, company_id: str, namespace: str | None, date_str: str) -> bool:
        key = self._revalidating_key(company_id=company_id, namespace=namespace, date_str=date_str)
        exists_count = await self._redis.exists(key)
        return exists_count == 1

    async def set_revalidating(
        self,
        company_id: str,
        namespace: str | None,
        date_str: str,
        ttl_seconds: int = 60 * 10,
    ) -> bool:
        key = self._revalidating_key(company_id=company_id, namespace=namespace, date_str=date_str)
        ok = await self._redis.set(key, datetime.now(UTC).isoformat(), ex=ttl_seconds, nx=True)
        return ok is True

    async def clear_revalidating(
        self, company_id: str, namespace: str | None, date_str: str
    ) -> None:
        key = self._revalidating_key(company_id=company_id, namespace=namespace, date_str=date_str)
        _ = await self._redis.delete(key)

    async def acquire_rebuild_lock(
        self,
        company_id: str,
        namespace: str | None,
        date_str: str,
        ttl_seconds: int = 60 * 3,
    ) -> bool:
        key = self._lock_key(company_id=company_id, namespace=namespace, date_str=date_str)
        ok = await self._redis.set(key, "1", ex=ttl_seconds, nx=True)
        return ok is True

    async def release_rebuild_lock(
        self, company_id: str, namespace: str | None, date_str: str
    ) -> None:
        key = self._lock_key(company_id=company_id, namespace=namespace, date_str=date_str)
        _ = await self._redis.delete(key)

    @classmethod
    def _period_segment(cls, date_from: str, date_to: str) -> str:
        return f"{date_from}__{date_to}"

    @classmethod
    def _period_state_key(
        cls,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        seg = cls._period_segment(date_from, date_to)
        return f"crm:period_summary:v1:{company_id}:{normalized_namespace}:{seg}:state"

    @classmethod
    def _period_lock_key(
        cls,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        seg = cls._period_segment(date_from, date_to)
        return f"crm:period_summary:v1:{company_id}:{normalized_namespace}:{seg}:lock"

    @classmethod
    def _period_revalidating_key(
        cls,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        seg = cls._period_segment(date_from, date_to)
        return f"crm:period_summary:v1:{company_id}:{normalized_namespace}:{seg}:revalidating"

    async def get_period_state(
        self,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> JsonObject | None:
        key = self._period_state_key(company_id, namespace, date_from, date_to)
        raw_value = await self._redis.get(key)
        if raw_value is None:
            return None
        return parse_json_object(raw_value, "period_summary.redis_state")

    async def set_period_state(
        self,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
        state: JsonObject,
        ttl_seconds: int = 60 * 60 * 24 * 7,
    ) -> None:
        key = self._period_state_key(company_id, namespace, date_from, date_to)
        ok = await self._redis.set(key, json.dumps(state, ensure_ascii=False), ex=ttl_seconds)
        if ok is not True:
            raise RuntimeError("Redis SET period summary state returned false")

    async def is_period_revalidating(
        self,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> bool:
        key = self._period_revalidating_key(company_id, namespace, date_from, date_to)
        exists_count = await self._redis.exists(key)
        return exists_count == 1

    async def set_period_revalidating(
        self,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
        ttl_seconds: int = 60 * 10,
    ) -> bool:
        key = self._period_revalidating_key(company_id, namespace, date_from, date_to)
        ok = await self._redis.set(key, datetime.now(UTC).isoformat(), ex=ttl_seconds, nx=True)
        return ok is True

    async def clear_period_revalidating(
        self,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> None:
        key = self._period_revalidating_key(company_id, namespace, date_from, date_to)
        _ = await self._redis.delete(key)

    async def acquire_period_rebuild_lock(
        self,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
        ttl_seconds: int = 60 * 5,
    ) -> bool:
        key = self._period_lock_key(company_id, namespace, date_from, date_to)
        ok = await self._redis.set(key, "1", ex=ttl_seconds, nx=True)
        return ok is True

    async def release_period_rebuild_lock(
        self,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> None:
        key = self._period_lock_key(company_id, namespace, date_from, date_to)
        _ = await self._redis.delete(key)
