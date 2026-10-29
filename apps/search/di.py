"""DI процесса search: провайдеры поиска, индексы и crawl API."""

from typing import Annotated

from apps.search.config import (
    SearchCrawlConfig,
    SearchCrawlEnrichmentConfig,
    SearchIndexProviderConfig,
    SearchIntegrationConfig,
    SearchSettings,
)
from apps.search.services.crawl.fetch_service import CrawlFetchService
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from apps.search.services.crawl.report_service import CrawlReportService
from apps.search.services.crawl_service import SearchCrawlService
from apps.search.services.enrichment import SearchResultInsightService, SearchSuggestionService
from apps.search.services.meta import MetaSearchService
from apps.search.services.provider_availability import ProviderAvailabilityStore
from apps.search.services.search_index_service import SearchIndexService
from apps.search.services.serp_cache import SerpCacheService
from core.clients.browser_fetch_client import BrowserFetchClient
from core.clients.rag_client import RagClient
from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClient
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi


@recipe
def search_integration(settings: SearchSettings) -> SearchIntegrationConfig:
    return settings.search


@recipe
def search_index_provider_config(search_integration: SearchIntegrationConfig) -> SearchIndexProviderConfig:
    return search_integration.index


@recipe
def crawl_config(settings: SearchSettings) -> SearchCrawlConfig:
    return settings.crawl


@recipe
def crawl_enrichment_config(crawl_config: SearchCrawlConfig) -> SearchCrawlEnrichmentConfig:
    return crawl_config.enrichment


@recipe
def rag_client(service_client: ServiceClient) -> RagClient:
    return RagClient(service_client)


@recipe
def provider_availability_store(
    redis_client: RedisClient,
    search_integration: SearchIntegrationConfig,
) -> ProviderAvailabilityStore:
    return ProviderAvailabilityStore(
        redis_client,
        key_prefix=search_integration.provider_state_key_prefix,
        available_ttl_seconds=search_integration.available_ttl_seconds,
        unavailable_ttl_seconds=search_integration.unavailable_ttl_seconds,
    )


@recipe
def serp_cache_service(
    redis_client: RedisClient,
    search_integration: SearchIntegrationConfig,
) -> SerpCacheService:
    return SerpCacheService(
        redis_client,
        key_prefix=search_integration.serp_cache_key_prefix,
        ttl_seconds=search_integration.serp_cache_ttl_seconds,
    )


@recipe
def crawl_fetch_service(
    browser_fetch_client: BrowserFetchClient,
    crawl_config: SearchCrawlConfig,
) -> CrawlFetchService:
    return CrawlFetchService(
        browser_fetch_client=browser_fetch_client,
        browser_fetch_timeout_seconds=crawl_config.browser_fetch_timeout_seconds,
    )


SEARCH_RECIPES = (
    search_integration,
    search_index_provider_config,
    crawl_config,
    crawl_enrichment_config,
    rag_client,
    provider_availability_store,
    serp_cache_service,
    crawl_fetch_service,
)


class SearchDi(PlatformDi, recipes=SEARCH_RECIPES):
    crawl_orchestrator_service: CrawlOrchestratorService
    crawl_report_service: CrawlReportService
    crawl_service: SearchCrawlService
    meta_search_service: MetaSearchService
    search_index_service: SearchIndexService
    search_result_insight_service: SearchResultInsightService
    search_suggestion_service: SearchSuggestionService


Di = Annotated[SearchDi, http_di(SearchDi), task_di(SearchDi)]
