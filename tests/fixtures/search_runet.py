"""Idempotent runet platform index seed for search integration tests."""

from apps.search.config import get_search_settings
from apps.search.di import SearchDi
from apps.search.services.crawl.bootstrap_service import ensure_runet_platform_seeded
from core.di import open_di
from core.di.kit import ProcessIdentity
from core.files.urls import resolve_files_route_segment


async def ensure_runet_platform_index_seeded() -> None:
    async with open_di(
        SearchDi,
        settings=get_search_settings(),
        identity=ProcessIdentity(
            service_name="search",
            files_route_segment=resolve_files_route_segment("search"),
        ),
        database="search_url",
    ):
        await ensure_runet_platform_seeded()
