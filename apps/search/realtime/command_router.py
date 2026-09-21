"""Регистрация WS command-handler'ов search в `core.websocket`."""

from __future__ import annotations

from apps.search.container import SearchContainer, get_search_container
from apps.search.realtime.operations import (
    CrawlDomainCreatePayload,
    CrawlDomainRefPayload,
    CrawlDomainsListPayload,
    CrawlDomainUpdatePayload,
    CrawlDomainUrlsAddPayload,
    CrawlJobIdPayload,
    CrawlJobsListPayload,
    CrawlProfileIdPayload,
    CrawlProfileTrancoSeedPayload,
    CrawlProfileUpdatePayload,
    CrawlUrlRefPayload,
    CrawlUrlsListPayload,
    SearchEmptyPayload,
    SearchIndexesListPayload,
    SearchIndexIdPayload,
    SearchIndexUpdatePayload,
    SearchPagePayload,
    SearchProviderIdPayload,
    SearchProviderOrderPayload,
    SearchProviderUpdatePayload,
    op_crawl_domains_create,
    op_crawl_domains_list,
    op_crawl_domains_remove,
    op_crawl_domains_run,
    op_crawl_domains_update,
    op_crawl_domains_urls_add,
    op_crawl_jobs_get,
    op_crawl_jobs_list,
    op_crawl_jobs_queue,
    op_crawl_profiles_create,
    op_crawl_profiles_list,
    op_crawl_profiles_summary,
    op_crawl_profiles_tranco_seed,
    op_crawl_profiles_update,
    op_crawl_seed_import,
    op_crawl_urls_get,
    op_crawl_urls_list,
    op_crawl_urls_recrawl,
    op_indexes_batch_get,
    op_indexes_create,
    op_indexes_get,
    op_indexes_list,
    op_indexes_update,
    op_providers_list,
    op_providers_order_update,
    op_providers_reset,
    op_providers_update,
    op_query_providers_snapshot,
    op_query_search,
    op_query_serp_click,
    op_query_serp_more,
    op_query_serp_refine,
)
from core.crawl.models import CrawlJobCreateRequest, CrawlProfileCreateRequest, SeedImportRequest
from core.logging import get_logger
from core.search.index_models import SearchIndexBatchGetRequest, SearchIndexCreateRequest
from core.search.models import (
    MetaSearchRefineRequest,
    MetaSearchRequest,
    MetaSearchSerpMoreRequest,
    SerpClickEvent,
)
from core.websocket import Operation, RegisteredOperation, register_service_operations

logger = get_logger(__name__)

SEARCH_OPERATIONS: dict[str, RegisteredOperation[SearchContainer]] = {
    "search/crawl_profiles/list_requested": Operation(payload_model=SearchPagePayload, fn=op_crawl_profiles_list),
    "search/crawl_profiles/create_requested": Operation(
        payload_model=CrawlProfileCreateRequest, fn=op_crawl_profiles_create
    ),
    "search/crawl_profiles/update_requested": Operation(
        payload_model=CrawlProfileUpdatePayload, fn=op_crawl_profiles_update
    ),
    "search/crawl_profiles/summary_requested": Operation(
        payload_model=CrawlProfileIdPayload, fn=op_crawl_profiles_summary
    ),
    "search/crawl_profiles/tranco_seed_requested": Operation(
        payload_model=CrawlProfileTrancoSeedPayload, fn=op_crawl_profiles_tranco_seed
    ),
    "search/crawl_jobs/queue_requested": Operation(payload_model=CrawlJobCreateRequest, fn=op_crawl_jobs_queue),
    "search/crawl_jobs/list_requested": Operation(payload_model=CrawlJobsListPayload, fn=op_crawl_jobs_list),
    "search/crawl_jobs/get_requested": Operation(payload_model=CrawlJobIdPayload, fn=op_crawl_jobs_get),
    "search/crawl_domains/list_requested": Operation(payload_model=CrawlDomainsListPayload, fn=op_crawl_domains_list),
    "search/crawl_domains/create_requested": Operation(
        payload_model=CrawlDomainCreatePayload, fn=op_crawl_domains_create
    ),
    "search/crawl_domains/update_requested": Operation(
        payload_model=CrawlDomainUpdatePayload, fn=op_crawl_domains_update
    ),
    "search/crawl_domains/remove_requested": Operation(payload_model=CrawlDomainRefPayload, fn=op_crawl_domains_remove),
    "search/crawl_domains/run_requested": Operation(payload_model=CrawlDomainRefPayload, fn=op_crawl_domains_run),
    "search/crawl_domains/urls_add_requested": Operation(
        payload_model=CrawlDomainUrlsAddPayload, fn=op_crawl_domains_urls_add
    ),
    "search/crawl_urls/list_requested": Operation(payload_model=CrawlUrlsListPayload, fn=op_crawl_urls_list),
    "search/crawl_urls/get_requested": Operation(payload_model=CrawlUrlRefPayload, fn=op_crawl_urls_get),
    "search/crawl_urls/recrawl_requested": Operation(payload_model=CrawlUrlRefPayload, fn=op_crawl_urls_recrawl),
    "search/crawl_seed/import_requested": Operation(payload_model=SeedImportRequest, fn=op_crawl_seed_import),
    "search/indexes/list_requested": Operation(payload_model=SearchIndexesListPayload, fn=op_indexes_list),
    "search/indexes/get_requested": Operation(payload_model=SearchIndexIdPayload, fn=op_indexes_get),
    "search/indexes/create_requested": Operation(payload_model=SearchIndexCreateRequest, fn=op_indexes_create),
    "search/indexes/update_requested": Operation(payload_model=SearchIndexUpdatePayload, fn=op_indexes_update),
    "search/indexes/batch_get_requested": Operation(
        payload_model=SearchIndexBatchGetRequest, fn=op_indexes_batch_get
    ),
    "search/query/search_requested": Operation(payload_model=MetaSearchRequest, fn=op_query_search),
    "search/query/serp_more_requested": Operation(payload_model=MetaSearchSerpMoreRequest, fn=op_query_serp_more),
    "search/query/serp_refine_requested": Operation(
        payload_model=MetaSearchRefineRequest, fn=op_query_serp_refine
    ),
    "search/query/serp_click_requested": Operation(payload_model=SerpClickEvent, fn=op_query_serp_click),
    "search/query/providers_snapshot_requested": Operation(
        payload_model=SearchEmptyPayload, fn=op_query_providers_snapshot
    ),
    "search/providers/list_requested": Operation(payload_model=SearchEmptyPayload, fn=op_providers_list),
    "search/providers/update_requested": Operation(payload_model=SearchProviderUpdatePayload, fn=op_providers_update),
    "search/providers/order_update_requested": Operation(
        payload_model=SearchProviderOrderPayload, fn=op_providers_order_update
    ),
    "search/providers/reset_requested": Operation(payload_model=SearchProviderIdPayload, fn=op_providers_reset),
}


def register_search_ws_commands() -> None:
    register_service_operations(SEARCH_OPERATIONS, get_search_container)
    logger.info("command_router.registered", service="search", operations=len(SEARCH_OPERATIONS))
