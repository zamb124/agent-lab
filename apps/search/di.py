"""DI процесса search: провайдеры поиска, индексы и crawl API."""

from typing import Annotated

from apps.search.components import HTTP_RECIPES
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from apps.search.services.crawl.report_service import CrawlReportService
from apps.search.services.crawl_service import SearchCrawlService
from apps.search.services.enrichment import SearchResultInsightService, SearchSuggestionService
from apps.search.services.meta import MetaSearchService
from apps.search.services.search_index_service import SearchIndexService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class SearchDi(PlatformDi, recipes=HTTP_RECIPES):
    crawl_orchestrator_service: CrawlOrchestratorService
    crawl_report_service: CrawlReportService
    crawl_service: SearchCrawlService
    meta_search_service: MetaSearchService
    search_index_service: SearchIndexService
    search_result_insight_service: SearchResultInsightService
    search_suggestion_service: SearchSuggestionService


Di = Annotated[SearchDi, http_di(SearchDi), task_di(SearchDi)]
