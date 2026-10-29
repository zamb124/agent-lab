"""CrawlBootstrapService idempotency without TaskIQ."""

from datetime import UTC, datetime

import pytest

from apps.search.config import SearchCrawlConfig
from apps.search.services.crawl.bootstrap_service import CrawlBootstrapService
from apps.search.tasks.task_names import CRAWL_IMPORT_SEED_DOMAINS
from core.crawl.models import CrawlDomain, CrawlDomainSeed, CrawlProfileCreateRequest
from core.logging import clear_log_context, get_log_context
from core.search.index_models import SearchIndexCreateRequest
from core.tasks import TaskSpec
from tests.fixtures.taskiq_capture import taskiq_task_name
from tests.search.conftest import make_search_index_slug

pytestmark = pytest.mark.timeout(60, func_only=True)


async def _create_empty_profile(search_di, unique_id: str) -> str:
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]
    await search_di.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Bootstrap {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
        )
    )
    await search_di.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            browser_fallback_enabled=False,
        )
    )
    return crawl_profile_id


@pytest.mark.asyncio
async def test_bootstrap_skips_seed_when_domains_exist(
    search_di,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_empty_profile(search_di, unique_id)
    await CrawlDomain.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain="example.com", category="docs", domain_rank=1)],
        next_crawl_after=datetime.now(UTC),
    )
    before_count = await CrawlDomain.count_for_profile(crawl_profile_id)

    bootstrap = CrawlBootstrapService(
        crawl_config=SearchCrawlConfig(
            default_crawl_profile_id=crawl_profile_id,
            bootstrap_tranco_on_empty=True,
            tranco_seed_limit=5,
        ),
    )
    result = await bootstrap.ensure_crawl_pipeline_ready()

    assert result.action == "skipped_seed"
    assert result.domain_count == before_count
    after_count = await CrawlDomain.count_for_profile(crawl_profile_id)
    assert after_count == before_count


@pytest.mark.asyncio
async def test_bootstrap_queues_tranco_seed_when_profile_empty(
    search_di,
    search_system_context,
    unique_id,
    monkeypatch,
):
    _ = search_system_context
    crawl_profile_id = await _create_empty_profile(search_di, unique_id)
    queued: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def _capture_enqueue(task: TaskSpec | str, *args: object, **kwargs: object) -> None:
        queued.append((taskiq_task_name(task), args, kwargs))

    monkeypatch.setattr(
        "apps.search.services.crawl.bootstrap_service.enqueue",
        _capture_enqueue,
    )

    bootstrap = CrawlBootstrapService(
        crawl_config=SearchCrawlConfig(
            default_crawl_profile_id=crawl_profile_id,
            bootstrap_tranco_on_empty=True,
            tranco_seed_limit=5,
        ),
    )
    result = await bootstrap.ensure_crawl_pipeline_ready()

    assert result.action == "queued_seed"
    assert result.domain_count == 0
    assert len(queued) == 1
    task_name, args, kwargs = queued[0]
    assert task_name == CRAWL_IMPORT_SEED_DOMAINS.name
    assert args[0] == crawl_profile_id
    assert args[1] == "tranco"
    assert args[2] == 5
    assert kwargs["background_kind"] == "startup"


@pytest.mark.asyncio
async def test_bootstrap_disabled_does_not_queue_seed(
    search_di,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_empty_profile(search_di, unique_id)
    assert await CrawlDomain.count_for_profile(crawl_profile_id) == 0

    bootstrap = CrawlBootstrapService(
        crawl_config=SearchCrawlConfig(
            default_crawl_profile_id=crawl_profile_id,
            bootstrap_tranco_on_empty=False,
            tranco_seed_limit=5,
        ),
    )
    result = await bootstrap.ensure_crawl_pipeline_ready()

    assert result.action == "bootstrap_disabled"
    assert result.domain_count == 0
    assert await CrawlDomain.count_for_profile(crawl_profile_id) == 0


@pytest.mark.asyncio
async def test_bootstrap_enqueue_outside_request_scope(
    search_di,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_empty_profile(search_di, unique_id)
    clear_log_context()
    assert not get_log_context().get("request_id")

    bootstrap = CrawlBootstrapService(
        crawl_config=SearchCrawlConfig(
            default_crawl_profile_id=crawl_profile_id,
            bootstrap_tranco_on_empty=True,
            tranco_seed_limit=5,
        ),
    )
    result = await bootstrap.ensure_crawl_pipeline_ready()
    assert result.action == "queued_seed"
    assert result.domain_count == 0
