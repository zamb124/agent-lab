"""
Кэш и state для daily summary в Redis.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis


class DailySummaryCacheService:
    """Хранит состояние daily summary и lock в Redis."""

    def __init__(self, redis_url: str):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    @staticmethod
    def _normalize_namespace(namespace: Optional[str]) -> str:
        if namespace is None:
            return "all"
        if namespace.strip() == "":
            return "all"
        return namespace

    @classmethod
    def _state_key(cls, company_id: str, namespace: Optional[str], date_str: str) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        return f"crm:daily_summary:v1:{company_id}:{normalized_namespace}:{date_str}:state"

    @classmethod
    def _lock_key(cls, company_id: str, namespace: Optional[str], date_str: str) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        return f"crm:daily_summary:v1:{company_id}:{normalized_namespace}:{date_str}:lock"

    @classmethod
    def _revalidating_key(cls, company_id: str, namespace: Optional[str], date_str: str) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        return f"crm:daily_summary:v1:{company_id}:{normalized_namespace}:{date_str}:revalidating"

    async def get_state(self, company_id: str, namespace: Optional[str], date_str: str) -> Optional[dict[str, Any]]:
        key = self._state_key(company_id=company_id, namespace=namespace, date_str=date_str)
        raw_value = await self._redis.get(key)
        if raw_value is None:
            return None
        payload = json.loads(raw_value)
        if not isinstance(payload, dict):
            raise ValueError("Daily summary state in Redis must be dict")
        return payload

    async def set_state(
        self,
        company_id: str,
        namespace: Optional[str],
        date_str: str,
        state: dict[str, Any],
        ttl_seconds: int = 60 * 60 * 24 * 7,
    ) -> None:
        key = self._state_key(company_id=company_id, namespace=namespace, date_str=date_str)
        await self._redis.set(key, json.dumps(state), ex=ttl_seconds)

    async def is_revalidating(self, company_id: str, namespace: Optional[str], date_str: str) -> bool:
        key = self._revalidating_key(company_id=company_id, namespace=namespace, date_str=date_str)
        return await self._redis.exists(key) == 1

    async def set_revalidating(
        self,
        company_id: str,
        namespace: Optional[str],
        date_str: str,
        ttl_seconds: int = 60 * 10,
    ) -> bool:
        key = self._revalidating_key(company_id=company_id, namespace=namespace, date_str=date_str)
        return await self._redis.set(key, datetime.now(timezone.utc).isoformat(), ex=ttl_seconds, nx=True) is True

    async def clear_revalidating(self, company_id: str, namespace: Optional[str], date_str: str) -> None:
        key = self._revalidating_key(company_id=company_id, namespace=namespace, date_str=date_str)
        await self._redis.delete(key)

    async def acquire_rebuild_lock(
        self,
        company_id: str,
        namespace: Optional[str],
        date_str: str,
        ttl_seconds: int = 60 * 3,
    ) -> bool:
        key = self._lock_key(company_id=company_id, namespace=namespace, date_str=date_str)
        return await self._redis.set(key, "1", ex=ttl_seconds, nx=True) is True

    async def release_rebuild_lock(self, company_id: str, namespace: Optional[str], date_str: str) -> None:
        key = self._lock_key(company_id=company_id, namespace=namespace, date_str=date_str)
        await self._redis.delete(key)

    @classmethod
    def _period_segment(cls, date_from: str, date_to: str) -> str:
        return f"{date_from}__{date_to}"

    @classmethod
    def _period_state_key(
        cls,
        company_id: str,
        namespace: Optional[str],
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
        namespace: Optional[str],
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
        namespace: Optional[str],
        date_from: str,
        date_to: str,
    ) -> str:
        normalized_namespace = cls._normalize_namespace(namespace)
        seg = cls._period_segment(date_from, date_to)
        return f"crm:period_summary:v1:{company_id}:{normalized_namespace}:{seg}:revalidating"

    async def get_period_state(
        self,
        company_id: str,
        namespace: Optional[str],
        date_from: str,
        date_to: str,
    ) -> Optional[dict[str, Any]]:
        key = self._period_state_key(company_id, namespace, date_from, date_to)
        raw_value = await self._redis.get(key)
        if raw_value is None:
            return None
        payload = json.loads(raw_value)
        if not isinstance(payload, dict):
            raise ValueError("Period summary state in Redis must be dict")
        return payload

    async def set_period_state(
        self,
        company_id: str,
        namespace: Optional[str],
        date_from: str,
        date_to: str,
        state: dict[str, Any],
        ttl_seconds: int = 60 * 60 * 24 * 7,
    ) -> None:
        key = self._period_state_key(company_id, namespace, date_from, date_to)
        await self._redis.set(key, json.dumps(state), ex=ttl_seconds)

    async def is_period_revalidating(
        self,
        company_id: str,
        namespace: Optional[str],
        date_from: str,
        date_to: str,
    ) -> bool:
        key = self._period_revalidating_key(company_id, namespace, date_from, date_to)
        return await self._redis.exists(key) == 1

    async def set_period_revalidating(
        self,
        company_id: str,
        namespace: Optional[str],
        date_from: str,
        date_to: str,
        ttl_seconds: int = 60 * 10,
    ) -> bool:
        key = self._period_revalidating_key(company_id, namespace, date_from, date_to)
        return await self._redis.set(key, datetime.now(timezone.utc).isoformat(), ex=ttl_seconds, nx=True) is True

    async def clear_period_revalidating(
        self,
        company_id: str,
        namespace: Optional[str],
        date_from: str,
        date_to: str,
    ) -> None:
        key = self._period_revalidating_key(company_id, namespace, date_from, date_to)
        await self._redis.delete(key)

    async def acquire_period_rebuild_lock(
        self,
        company_id: str,
        namespace: Optional[str],
        date_from: str,
        date_to: str,
        ttl_seconds: int = 60 * 5,
    ) -> bool:
        key = self._period_lock_key(company_id, namespace, date_from, date_to)
        return await self._redis.set(key, "1", ex=ttl_seconds, nx=True) is True

    async def release_period_rebuild_lock(
        self,
        company_id: str,
        namespace: Optional[str],
        date_from: str,
        date_to: str,
    ) -> None:
        key = self._period_lock_key(company_id, namespace, date_from, date_to)
        await self._redis.delete(key)
