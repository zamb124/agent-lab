"""Crawl bootstrap end-to-end via real TaskIQ search worker."""

import pytest

from apps.search.tasks.task_names import CRAWL_IMPORT_SEED_DOMAINS
from apps.search.models import CrawlDomain, CrawlProfileCreateRequest
from core.search.index_models import SearchIndexCreateRequest
from core.tasks import enqueue
from tests.fixtures.taskiq_timeouts import TASKIQ_WAIT_RESULT_TIMEOUT_SECONDS
from tests.search.conftest import make_search_index_slug

pytestmark = [
    pytest.mark.integration,
    pytest.mark.network,
    pytest.mark.real_taskiq,
    pytest.mark.timeout(300, func_only=True),
]

_TRANCO_IMPORT_LIMIT = 15
_TASKIQ_WAIT_SECONDS = max(TASKIQ_WAIT_RESULT_TIMEOUT_SECONDS, 180)


@pytest.mark.asyncio
async def test_bootstrap_queues_tranco_import_via_search_worker(
    search_di,
    search_worker,
    search_system_context,
    unique_id,
):
    """search_worker исполняет crawl_import_seed_domains (Tranco HTTP).

    Постановка в очередь через CrawlBootstrapService — tests/search/integration/test_crawl_bootstrap_service.py.
    """
    _ = search_worker, search_system_context
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]

    await search_di.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Bootstrap e2e {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
        )
    )
    await search_di.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="tranco",
            browser_fallback_enabled=False,
        )
    )
    assert await CrawlDomain.count_for_profile(crawl_profile_id) == 0

    task = await enqueue(
        CRAWL_IMPORT_SEED_DOMAINS,
        crawl_profile_id,
        "tranco",
        _TRANCO_IMPORT_LIMIT,
            background_kind="background",
        )
    worker_result = await task.wait_result(timeout=_TASKIQ_WAIT_SECONDS)
    assert not worker_result.is_err, f"tranco import task failed: {worker_result.error}"
    import_payload = worker_result.return_value
    assert import_payload["imported"] >= 1, import_payload

    domain_count = await CrawlDomain.count_for_profile(crawl_profile_id)
    assert domain_count >= 1

    page = await CrawlDomain.page_by_domain_asc(
        crawl_profile_id=crawl_profile_id,
        status=None,
        limit=10,
        offset=0,
    )
    assert page.items
