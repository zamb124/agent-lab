"""Redis-backed SERP pool cache for infinite scroll."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import Field

from core.clients.redis_client import RedisClient
from core.models import StrictBaseModel
from core.search.models import SearchMode, WebSearchResult


class SerpCacheEntry(StrictBaseModel):
    query: str = Field(..., min_length=1)
    mode: SearchMode
    index_ids: list[str] = Field(default_factory=list)
    ranked: list[WebSearchResult] = Field(default_factory=list)
    created_at: datetime


class SerpCacheMissError(LookupError):
    pass


class SerpCacheService:
    def __init__(self, redis_client: RedisClient, *, key_prefix: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("serp cache ttl_seconds must be positive")
        self._redis_client: RedisClient = redis_client
        self._key_prefix: str = key_prefix
        self._ttl_seconds: int = ttl_seconds

    def _redis_key(self, serp_cache_key: str) -> str:
        token = serp_cache_key.strip()
        if not token:
            raise ValueError("serp_cache_key is required")
        return f"{self._key_prefix}:{token}"

    async def store_pool(
        self,
        *,
        query: str,
        mode: SearchMode,
        index_ids: list[str],
        ranked: list[WebSearchResult],
    ) -> str:
        if not ranked:
            raise ValueError("ranked SERP pool must not be empty")
        serp_cache_key = uuid.uuid4().hex
        entry = SerpCacheEntry(
            query=query,
            mode=mode,
            index_ids=list(index_ids),
            ranked=ranked,
            created_at=datetime.now(UTC),
        )
        _ = await self._redis_client.set(
            self._redis_key(serp_cache_key),
            entry.model_dump_json(),
            ttl=self._ttl_seconds,
        )
        return serp_cache_key

    async def load_entry(self, serp_cache_key: str) -> SerpCacheEntry:
        raw = await self._redis_client.get(self._redis_key(serp_cache_key))
        if raw is None:
            raise SerpCacheMissError(f"serp cache expired or missing: {serp_cache_key}")
        return SerpCacheEntry.model_validate_json(raw)

    async def slice(
        self,
        serp_cache_key: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[WebSearchResult], int, bool, str]:
        if offset < 0:
            raise ValueError("offset must be >= 0")
        if limit <= 0:
            raise ValueError("limit must be > 0")
        entry = await self.load_entry(serp_cache_key)
        total_count = len(entry.ranked)
        page_items = entry.ranked[offset : offset + limit]
        ranked_page: list[WebSearchResult] = []
        for rank, item in enumerate(page_items, start=offset + 1):
            ranked_page.append(item.model_copy(update={"rank": rank}))
        has_more = offset + len(page_items) < total_count
        return ranked_page, total_count, has_more, entry.query
