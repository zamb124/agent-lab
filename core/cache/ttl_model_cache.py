"""Small async TTL cache for Pydantic models backed by Redis."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from core.logging import get_logger

logger = get_logger(__name__)


class RedisTextCache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool: ...


TModel = TypeVar("TModel", bound=BaseModel)


class TtlModelCache(Generic[TModel]):
    """Process memory cache with Redis as a shared backing store."""

    def __init__(
        self,
        *,
        name: str,
        model_type: type[TModel],
        redis_client_factory: Callable[[], RedisTextCache],
    ) -> None:
        self._name: str = name
        self._model_type: type[TModel] = model_type
        self._redis_client_factory: Callable[[], RedisTextCache] = redis_client_factory
        self._lock: asyncio.Lock = asyncio.Lock()
        self._memory_cache: tuple[str, float, TModel] | None = None

    async def get_or_build(
        self,
        *,
        enabled: bool,
        key: str,
        ttl_seconds: int,
        builder: Callable[[], Awaitable[TModel]],
    ) -> TModel:
        if not enabled:
            return await builder()

        cached = self._get_memory(key)
        if cached is not None:
            return cached

        async with self._lock:
            cached = self._get_memory(key)
            if cached is not None:
                return cached

            payload = await self._get_redis(key)
            if payload:
                try:
                    model = self._model_type.model_validate_json(payload)
                    self._set_memory(key, ttl_seconds, model)
                    return model
                except ValidationError as exc:
                    logger.warning("%s.invalid_payload", self._name, error=str(exc))

            model = await builder()
            await self._set_redis(key, model.model_dump_json(), ttl_seconds)
            self._set_memory(key, ttl_seconds, model)
            return model

    def _get_memory(self, key: str) -> TModel | None:
        if self._memory_cache is None:
            return None
        cached_key, expires_at, model = self._memory_cache
        if cached_key != key:
            return None
        if expires_at <= time.monotonic():
            self._memory_cache = None
            return None
        return model

    def _set_memory(self, key: str, ttl_seconds: int, model: TModel) -> None:
        self._memory_cache = (key, time.monotonic() + ttl_seconds, model)

    async def _get_redis(self, key: str) -> str | None:
        return await self._redis_client_factory().get(key)

    async def _set_redis(self, key: str, value: str, ttl_seconds: int) -> None:
        ok = await self._redis_client_factory().set(key, value, ttl=ttl_seconds)
        if not ok:
            logger.warning("%s.redis_set_failed", self._name)
