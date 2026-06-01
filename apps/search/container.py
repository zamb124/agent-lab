"""DI container for search service."""

from __future__ import annotations

from apps.search.config import SearchSettings, get_search_settings
from apps.search.services import (
    MetaSearchService,
    ProviderAvailabilityStore,
    SearchResultInsightService,
    SearchSuggestionService,
)
from core.clients.redis_client import RedisClient
from core.container import BaseContainer, ContainerRegistry, lazy


class SearchContainer(BaseContainer):
    """Search service composition root."""

    @lazy
    def redis_client(self) -> RedisClient:
        settings = get_search_settings()
        return RedisClient(settings.database.redis_url)

    @lazy
    def provider_availability_store(self) -> ProviderAvailabilityStore:
        config = get_search_settings().search
        return ProviderAvailabilityStore(
            self.redis_client,
            key_prefix=config.provider_state_key_prefix,
            available_ttl_seconds=config.available_ttl_seconds,
            unavailable_ttl_seconds=config.unavailable_ttl_seconds,
        )

    @lazy
    def meta_search_service(self) -> MetaSearchService:
        return MetaSearchService(
            get_search_settings().search,
            self.provider_availability_store,
            self.billing_service,
        )

    @lazy
    def search_suggestion_service(self) -> SearchSuggestionService:
        return SearchSuggestionService()

    @lazy
    def search_result_insight_service(self) -> SearchResultInsightService:
        return SearchResultInsightService()


def _build_search_container(settings: SearchSettings) -> SearchContainer:
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required для сервиса search")
    return SearchContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


def _create_search_container() -> SearchContainer:
    return _build_search_container(get_search_settings())


_search_registry: ContainerRegistry[SearchContainer] = ContainerRegistry(
    _create_search_container,
    name="SearchContainer",
)

get_search_container = _search_registry.get
reset_search_container = _search_registry.reset
