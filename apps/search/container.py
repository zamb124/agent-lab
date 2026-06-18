"""DI container for search service."""

from __future__ import annotations

from apps.search.config import SearchSettings, get_search_settings
from apps.search.db.base import SearchDatabase
from apps.search.db.crawl_repositories import (
    CrawlDomainRepository,
    CrawlJobRepository,
    CrawlProfileRepository,
    CrawlUrlRepository,
)
from apps.search.db.search_index_repository import SearchIndexRepository
from apps.search.providers.index import IndexSearchProvider
from apps.search.services import (
    MetaSearchService,
    ProviderAvailabilityStore,
    SearchResultInsightService,
    SearchSuggestionService,
)
from apps.search.services.crawl.bootstrap_service import CrawlBootstrapService
from apps.search.services.crawl.fetch_service import CrawlFetchService
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from apps.search.services.crawl.page_enrichment_service import CrawlPageEnrichmentService
from apps.search.services.crawl.report_service import CrawlReportService
from apps.search.services.crawl_service import SearchCrawlService
from apps.search.services.search_index_service import SearchIndexService
from apps.search.services.serp_cache import SerpCacheService
from apps.search.services.system_context import build_search_system_context
from core.clients.browser_fetch_client import BrowserFetchClient
from core.clients.rag_client import RagClient
from core.clients.redis_client import RedisClient
from core.container import BaseContainer, ContainerRegistry, lazy


class SearchContainer(BaseContainer):
    """Search service composition root."""

    @lazy
    def search_database(self) -> SearchDatabase:
        settings = get_search_settings()
        if not settings.database.search_url:
            raise ValueError("database.search_url is required")
        return SearchDatabase.get_instance(settings.database.search_url)

    @lazy
    def redis_client(self) -> RedisClient:
        settings = get_search_settings()
        return RedisClient(settings.database.redis_url)

    @lazy
    def search_index_repository(self) -> SearchIndexRepository:
        return SearchIndexRepository(self.search_database)

    @lazy
    def crawl_profile_repository(self) -> CrawlProfileRepository:
        return CrawlProfileRepository(self.search_database)

    @lazy
    def crawl_domain_repository(self) -> CrawlDomainRepository:
        return CrawlDomainRepository(self.search_database)

    @lazy
    def crawl_url_repository(self) -> CrawlUrlRepository:
        return CrawlUrlRepository(self.search_database)

    @lazy
    def crawl_job_repository(self) -> CrawlJobRepository:
        return CrawlJobRepository(self.search_database)

    @lazy
    def rag_client(self) -> RagClient:
        return RagClient(self.service_client)

    @lazy
    def provider_availability_store(self) -> ProviderAvailabilityStore:
        config = get_search_settings().search
        return ProviderAvailabilityStore(
            self.redis_client,
            key_prefix=config.provider_state_key_prefix,
            available_ttl_seconds=config.available_ttl_seconds,
            unavailable_ttl_seconds=config.unavailable_ttl_seconds,
        )

    async def _build_index_system_context(self, trace_id: str):
        return await build_search_system_context(
            trace_id=trace_id,
            company_repository=self.company_repository,
            subdomain_repository=self.subdomain_repository,
            user_repository=self.user_repository,
        )

    @lazy
    def index_search_provider(self) -> IndexSearchProvider:
        return IndexSearchProvider(
            get_search_settings().search.index,
            self.search_index_repository,
            self.rag_client,
            self._build_index_system_context,
        )

    @lazy
    def serp_cache_service(self) -> SerpCacheService:
        config = get_search_settings().search
        return SerpCacheService(
            self.redis_client,
            key_prefix=config.serp_cache_key_prefix,
            ttl_seconds=config.serp_cache_ttl_seconds,
        )

    @lazy
    def meta_search_service(self) -> MetaSearchService:
        return MetaSearchService(
            get_search_settings().search,
            self.provider_availability_store,
            self.billing_service,
            self.index_search_provider,
            self.serp_cache_service,
        )

    @lazy
    def search_index_service(self) -> SearchIndexService:
        return SearchIndexService(
            self.search_index_repository,
            self.rag_client,
        )

    @lazy
    def crawl_service(self) -> SearchCrawlService:
        return SearchCrawlService(
            self.crawl_profile_repository,
            self.crawl_domain_repository,
            self.crawl_url_repository,
            self.crawl_job_repository,
            self.crawl_orchestrator_service,
        )

    @lazy
    def crawl_bootstrap_service(self) -> CrawlBootstrapService:
        return CrawlBootstrapService(
            crawl_profile_repository=self.crawl_profile_repository,
            crawl_domain_repository=self.crawl_domain_repository,
            crawl_url_repository=self.crawl_url_repository,
            crawl_job_repository=self.crawl_job_repository,
            crawl_config=get_search_settings().crawl,
        )

    @lazy
    def browser_fetch_client(self) -> BrowserFetchClient:
        return BrowserFetchClient(self.service_client)

    @lazy
    def crawl_fetch_service(self) -> CrawlFetchService:
        crawl_config = get_search_settings().crawl
        return CrawlFetchService(
            browser_fetch_client=self.browser_fetch_client,
            browser_fetch_timeout_seconds=crawl_config.browser_fetch_timeout_seconds,
        )

    @lazy
    def crawl_page_enrichment_service(self) -> CrawlPageEnrichmentService:
        return CrawlPageEnrichmentService(get_search_settings().crawl.enrichment)

    @lazy
    def crawl_orchestrator_service(self) -> CrawlOrchestratorService:
        return CrawlOrchestratorService(
            crawl_profile_repository=self.crawl_profile_repository,
            crawl_domain_repository=self.crawl_domain_repository,
            crawl_url_repository=self.crawl_url_repository,
            crawl_job_repository=self.crawl_job_repository,
            fetch_service=self.crawl_fetch_service,
            page_enrichment_service=self.crawl_page_enrichment_service,
            rag_client=self.rag_client,
            build_system_context=self._build_index_system_context,
            crawl_config=get_search_settings().crawl,
        )

    @lazy
    def crawl_report_service(self) -> CrawlReportService:
        return CrawlReportService(
            crawl_profile_repository=self.crawl_profile_repository,
            crawl_domain_repository=self.crawl_domain_repository,
            crawl_url_repository=self.crawl_url_repository,
            crawl_job_repository=self.crawl_job_repository,
            rag_client=self.rag_client,
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
    if not settings.database.search_url:
        raise ValueError("database.search_url is required для сервиса search")
    return SearchContainer(
        db_url=settings.database.search_url,
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
