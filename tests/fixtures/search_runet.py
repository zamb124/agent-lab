"""Idempotent runet platform index seed for search integration tests."""

from filelock import FileLock

from apps.search.container import get_search_container, reset_search_container
from apps.search.errors import SearchIndexNotFoundError
from core.crawl.models import CrawlProfileCreateRequest
from core.search.index_models import SearchIndexCreateRequest

_RUNET_INDEX_SEED_LOCK = "/tmp/platform_test_runet_index_seed.lock"
_RUNET_INDEX_SEED_LOCK_TIMEOUT_SEC = 300


async def ensure_runet_platform_index_seeded() -> None:
    lock = FileLock(_RUNET_INDEX_SEED_LOCK, timeout=_RUNET_INDEX_SEED_LOCK_TIMEOUT_SEC)
    with lock:
        reset_search_container()
        container = get_search_container()
        try:
            _ = await container.search_index_repository.get("runet", company_id="system")
        except SearchIndexNotFoundError:
            _ = await container.search_index_repository.create(
                "system",
                SearchIndexCreateRequest(
                    search_index_id="runet",
                    display_name="Runet Web",
                    description="Платформенный индекс русскоязычного веба",
                    rag_namespace_id="runet:platform",
                    rag_collection_id="runet",
                    search_enabled=True,
                    indexing_profile_key="runet_web",
                ),
            )
        try:
            _ = await container.crawl_profile_repository.get_with_index("runet_platform")
        except ValueError:
            _ = await container.crawl_service.create_profile(
                CrawlProfileCreateRequest(
                    crawl_profile_id="runet_platform",
                    search_index_id="runet",
                    seed_source="tranco",
                    browser_fallback_enabled=True,
                )
            )
