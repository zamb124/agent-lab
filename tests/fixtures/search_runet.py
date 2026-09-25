"""Idempotent runet platform index seed for search integration tests."""

from datetime import UTC, datetime

from oxyde.exceptions import IntegrityError

from apps.search.config import get_search_settings
from apps.search.di import SearchDi
from apps.search.errors import SearchIndexNotFoundError
from core.crawl.models import CrawlProfile, CrawlProfileCreateRequest
from core.di import open_di
from core.di.kit import ProcessIdentity
from core.files.urls import resolve_files_route_segment
from core.search.index_models import SearchIndexDefinition


async def ensure_runet_platform_index_seeded() -> None:
    async with open_di(
        SearchDi,
        settings=get_search_settings(),
        identity=ProcessIdentity(
            service_name="search",
            files_route_segment=resolve_files_route_segment("search"),
        ),
        database="search_url",
    ) as di:
        await _seed_runet_platform_index(di)


async def _seed_runet_platform_index(di) -> None:
    try:
        _ = await di.search_index_service.get("runet", company_id="system")
    except SearchIndexNotFoundError:
        now = datetime.now(UTC)
        try:
            _ = await SearchIndexDefinition.create(
                SearchIndexDefinition(
                    search_index_id="runet",
                    company_id="system",
                    display_name="Runet Web",
                    description="Платформенный индекс русскоязычного веба",
                    rag_namespace_id="runet:platform",
                    rag_collection_id="runet",
                    search_enabled=True,
                    indexing_profile_key="runet_web",
                    created_at=now,
                    updated_at=now,
                ),
            )
        except IntegrityError:
            pass
    try:
        _ = await CrawlProfile.get_with_index("runet_platform")
    except ValueError:
        try:
            _ = await di.crawl_service.create_profile(
                CrawlProfileCreateRequest(
                    crawl_profile_id="runet_platform",
                    search_index_id="runet",
                    seed_source="tranco",
                    browser_fallback_enabled=True,
                )
            )
        except IntegrityError:
            pass
