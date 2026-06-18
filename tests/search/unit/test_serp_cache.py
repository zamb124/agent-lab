"""SERP Redis cache unit tests."""

import pytest

from apps.search.services.serp_cache import SerpCacheMissError, SerpCacheService
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.search.models import WebSearchResult

pytestmark = pytest.mark.unit


def _sample_result(rank: int) -> WebSearchResult:
    return WebSearchResult(
        title=f"Title {rank}",
        url=f"https://example.com/page-{rank}",
        snippet=f"Snippet {rank}",
        display_url="example.com",
        provider="index",
        provider_rank=rank,
        rank=rank,
        score=1.0 / rank,
    )


@pytest.mark.asyncio
async def test_serp_cache_store_and_slice(unique_id) -> None:
    redis_client = RedisClient(get_settings().database.redis_url)
    await redis_client.connect()
    service = SerpCacheService(
        redis_client,
        key_prefix=f"test:search:serp:{unique_id}",
        ttl_seconds=120,
    )
    ranked = [_sample_result(index) for index in range(1, 26)]
    try:
        cache_key = await service.store_pool(
            query="humanitec",
            mode="quick",
            index_ids=["runet"],
            ranked=ranked,
        )
        page, total_count, has_more, query = await service.slice(cache_key, offset=10, limit=10)
        assert query == "humanitec"
        assert total_count == 25
        assert has_more is True
        assert len(page) == 10
        assert page[0].rank == 11
        assert page[0].title == "Title 11"
        tail, total_count_tail, has_more_tail, _ = await service.slice(cache_key, offset=20, limit=10)
        assert total_count_tail == 25
        assert has_more_tail is False
        assert len(tail) == 5
        assert tail[-1].rank == 25
    finally:
        await redis_client.close()


@pytest.mark.asyncio
async def test_serp_cache_missing_raises(unique_id) -> None:
    redis_client = RedisClient(get_settings().database.redis_url)
    await redis_client.connect()
    service = SerpCacheService(
        redis_client,
        key_prefix=f"test:search:serp:{unique_id}",
        ttl_seconds=120,
    )
    try:
        with pytest.raises(SerpCacheMissError):
            await service.slice("missing-cache-key", offset=0, limit=10)
    finally:
        await redis_client.close()
