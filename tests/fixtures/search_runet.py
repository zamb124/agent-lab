"""Idempotent runet platform index seed for search integration tests."""

from sqlalchemy.exc import IntegrityError

from apps.search.container import get_search_container, reset_search_container
from apps.search.errors import SearchIndexNotFoundError
from core.crawl.models import CrawlProfileCreateRequest
from core.search.index_models import SearchIndexCreateRequest


async def ensure_runet_platform_index_seeded() -> None:
    reset_search_container()
    container = get_search_container()
    try:
        _ = await container.search_index_repository.get("runet", company_id="system")
    except SearchIndexNotFoundError:
        try:
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
        except IntegrityError:
            pass
    try:
        _ = await container.crawl_profile_repository.get_with_index("runet_platform")
    except ValueError:
        try:
            _ = await container.crawl_service.create_profile(
                CrawlProfileCreateRequest(
                    crawl_profile_id="runet_platform",
                    search_index_id="runet",
                    seed_source="tranco",
                    browser_fallback_enabled=True,
                )
            )
        except IntegrityError:
            pass
