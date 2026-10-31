"""run_tick планирует backlog раньше cooldown и discover для due-домена без pending."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aiohttp import web

import apps.search.services.crawl.orchestrator_service as orchestrator_module
from apps.search.config import SearchCrawlConfig, get_search_settings
from apps.search.models import (
    CrawlDomain,
    CrawlDomainSeed,
    CrawlJob,
    CrawlProfile,
    CrawlProfileCreateRequest,
    CrawlUrl,
    SitemapEntry,
)
from apps.search.services.crawl.fetch_service import CrawlFetchService
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from apps.search.services.crawl.page_enrichment_service import CrawlPageEnrichmentService
from apps.search.services.crawl.politeness_service import CrawlPolitenessService
from core.clients.browser_fetch_client import BrowserFetchClient
from core.clients.rag_client import RagClient
from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.search.index_models import SearchIndexDefinition
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server
from tests.fixtures.taskiq_capture import taskiq_task_name


def _record_enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    recorded: list[tuple[object, ...]] = []

    async def record(task: object, *args: object, **kwargs: object) -> None:
        _ = kwargs
        recorded.append((taskiq_task_name(task), *args))

    monkeypatch.setattr(orchestrator_module, "enqueue", record)
    return recorded


def _orchestrator(crawl_config: SearchCrawlConfig) -> CrawlOrchestratorService:
    return CrawlOrchestratorService(
        fetch_service=CrawlFetchService(
            browser_fetch_client=BrowserFetchClient(ServiceClient()),
            browser_fetch_timeout_seconds=crawl_config.browser_fetch_timeout_seconds,
        ),
        page_enrichment_service=CrawlPageEnrichmentService(crawl_config.enrichment),
        politeness_service=CrawlPolitenessService(
            redis_client=RedisClient(get_settings().database.redis_url),
            crawl_config=crawl_config,
        ),
        rag_client=RagClient(),
        crawl_config=crawl_config,
    )


async def _seed_profile(unique_id: str, *, max_domains_per_tick: int) -> tuple[str, str]:
    now = datetime.now(UTC)
    search_index_id = f"tk-{unique_id}"[:64]
    crawl_profile_id = f"cr-{unique_id}"[:64]
    await SearchIndexDefinition.create(
        SearchIndexDefinition(
            search_index_id=search_index_id,
            company_id="system",
            display_name=f"Tick {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
            created_at=now,
            updated_at=now,
        )
    )
    await CrawlProfile.create(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            max_domains_per_tick=max_domains_per_tick,
            max_urls_per_batch=5,
            http_concurrency=2,
            browser_fallback_enabled=False,
        )
    )
    return search_index_id, crawl_profile_id


async def _cleanup_profile(search_index_id: str, crawl_profile_id: str) -> None:
    domains = await CrawlDomain.objects.filter(crawl_profile_id=crawl_profile_id).all()
    for domain in domains:
        urls = await CrawlUrl.objects.filter(crawl_domain_id=domain.crawl_domain_id).all()
        for url in urls:
            _ = await CrawlUrl.delete_by_id(url.crawl_url_id)
        _ = await CrawlDomain.delete_by_id(domain.crawl_domain_id)
    jobs = await CrawlJob.objects.filter(crawl_profile_id=crawl_profile_id).all()
    for job in jobs:
        _ = await CrawlJob.delete_by_id(job.crawl_job_id)
    _ = await CrawlProfile.delete_by_id(crawl_profile_id)
    _ = await SearchIndexDefinition.delete_by_id(search_index_id)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_run_tick_prioritizes_backlog_over_cooldown(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    now = datetime.now(UTC)
    search_index_id, crawl_profile_id = await _seed_profile(unique_id, max_domains_per_tick=2)
    backlog_name = f"{unique_id}-backlog.example".lower()
    due_name = f"{unique_id}-due.example".lower()
    await CrawlDomain.upsert_seed_batch(
        crawl_profile_id,
        [
            CrawlDomainSeed(domain=backlog_name, category="docs", domain_rank=1),
            CrawlDomainSeed(domain=due_name, category="docs", domain_rank=2),
        ],
        next_crawl_after=now + timedelta(hours=6),
    )
    backlog = await CrawlDomain.objects.filter(
        crawl_profile_id=crawl_profile_id,
        domain=backlog_name,
    ).get()
    due = await CrawlDomain.objects.filter(
        crawl_profile_id=crawl_profile_id,
        domain=due_name,
    ).get()
    _ = await CrawlDomain.objects.filter(crawl_domain_id=due.crawl_domain_id).update(
        using="search",
        next_crawl_after=now - timedelta(minutes=1),
    )
    _ = await CrawlUrl.upsert_from_sitemap(
        backlog.crawl_domain_id,
        [
            SitemapEntry(url=f"https://{backlog_name}/a"),
            SitemapEntry(url=f"https://{backlog_name}/b"),
        ],
    )
    recorded = _record_enqueued(monkeypatch)
    try:
        result = await _orchestrator(get_search_settings().crawl).run_tick(
            crawl_profile_id=crawl_profile_id,
            trigger="manual",
            schedule_task_id=None,
        )
        fetch_tasks = [item for item in recorded if item[0] == "crawl_fetch_url"]
        discover_tasks = [item for item in recorded if item[0] == "crawl_discover_domain"]
        ticks = [item for item in recorded if item[0] == "crawl_orchestrator_tick"]
        assert result["domains_scheduled"] == 2
        assert len(fetch_tasks) == 2
        assert {item[1] for item in fetch_tasks} == {backlog.crawl_domain_id}
        assert len(discover_tasks) == 1
        assert discover_tasks[0][1] == due.crawl_domain_id
        assert ticks == []
    finally:
        await _cleanup_profile(search_index_id, crawl_profile_id)


_THIN_HTML = (
    "<html><head><title>Thin</title></head>"
    "<body><p>Short crawl extract.</p></body></html>"
)


def _thin_app() -> web.Application:
    async def page(_request: web.Request) -> web.Response:
        return web.Response(text=_THIN_HTML, content_type="text/html")

    app = web.Application()
    app.router.add_get("/{tail:.*}", page)
    return app


def _quiet_crawl_config() -> SearchCrawlConfig:
    return get_search_settings().crawl.model_copy(update={"politeness_enabled": False})


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_fetch_one_url_reenqueues_while_pending(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    search_index_id, crawl_profile_id = await _seed_profile(unique_id, max_domains_per_tick=2)
    domain_name = f"{unique_id}-fetch.example".lower()
    await CrawlDomain.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=domain_name, category="docs", domain_rank=1)],
        next_crawl_after=datetime.now(UTC),
    )
    domain = await CrawlDomain.objects.filter(
        crawl_profile_id=crawl_profile_id,
        domain=domain_name,
    ).get()
    job = await CrawlJob.start(crawl_profile_id, "manual", None)
    recorded = _record_enqueued(monkeypatch)
    try:
        async with ephemeral_web_server(_thin_app()) as base_url:
            _ = await CrawlUrl.upsert_from_sitemap(
                domain.crawl_domain_id,
                [
                    SitemapEntry(url=f"{base_url}/a"),
                    SitemapEntry(url=f"{base_url}/b"),
                ],
            )
            await _orchestrator(_quiet_crawl_config()).fetch_one_url(
                domain.crawl_domain_id,
                job.crawl_job_id,
                crawl_profile_id,
                1,
            )
        fetch_tasks = [item for item in recorded if item[0] == "crawl_fetch_url"]
        assert fetch_tasks == [
            ("crawl_fetch_url", domain.crawl_domain_id, job.crawl_job_id, crawl_profile_id, 1)
        ]
        refreshed = await CrawlDomain.get(domain.crawl_domain_id)
        assert refreshed is not None
        assert refreshed.last_crawled_at is None
    finally:
        await _cleanup_profile(search_index_id, crawl_profile_id)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_fetch_one_url_enqueues_tick_when_domain_drained_but_profile_pending(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    search_index_id, crawl_profile_id = await _seed_profile(unique_id, max_domains_per_tick=2)
    drained_name = f"{unique_id}-drained.example".lower()
    other_name = f"{unique_id}-other.example".lower()
    await CrawlDomain.upsert_seed_batch(
        crawl_profile_id,
        [
            CrawlDomainSeed(domain=drained_name, category="docs", domain_rank=1),
            CrawlDomainSeed(domain=other_name, category="docs", domain_rank=2),
        ],
        next_crawl_after=datetime.now(UTC),
    )
    drained = await CrawlDomain.objects.filter(
        crawl_profile_id=crawl_profile_id,
        domain=drained_name,
    ).get()
    other = await CrawlDomain.objects.filter(
        crawl_profile_id=crawl_profile_id,
        domain=other_name,
    ).get()
    job = await CrawlJob.start(crawl_profile_id, "manual", None)
    recorded = _record_enqueued(monkeypatch)
    try:
        async with ephemeral_web_server(_thin_app()) as base_url:
            _ = await CrawlUrl.upsert_from_sitemap(
                drained.crawl_domain_id,
                [SitemapEntry(url=f"{base_url}/only")],
            )
            _ = await CrawlUrl.upsert_from_sitemap(
                other.crawl_domain_id,
                [SitemapEntry(url=f"https://{other_name}/still-pending")],
            )
            await _orchestrator(_quiet_crawl_config()).fetch_one_url(
                drained.crawl_domain_id,
                job.crawl_job_id,
                crawl_profile_id,
                1,
            )
        fetch_tasks = [item for item in recorded if item[0] == "crawl_fetch_url"]
        ticks = [item for item in recorded if item[0] == "crawl_orchestrator_tick"]
        assert fetch_tasks == []
        assert ticks == [("crawl_orchestrator_tick", crawl_profile_id)]
        refreshed = await CrawlDomain.get(drained.crawl_domain_id)
        assert refreshed is not None
        assert refreshed.last_crawled_at is not None
    finally:
        await _cleanup_profile(search_index_id, crawl_profile_id)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_run_tick_does_not_reenqueue_when_no_domains_scheduled(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    now = datetime.now(UTC)
    search_index_id, crawl_profile_id = await _seed_profile(unique_id, max_domains_per_tick=1)
    domain_name = f"{unique_id}-future.example".lower()
    await CrawlDomain.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=domain_name, category="docs", domain_rank=1)],
        next_crawl_after=now + timedelta(hours=6),
    )
    recorded = _record_enqueued(monkeypatch)
    try:
        result = await _orchestrator(get_search_settings().crawl).run_tick(
            crawl_profile_id=crawl_profile_id,
            trigger="manual",
            schedule_task_id=None,
        )
        ticks = [item for item in recorded if item[0] == "crawl_orchestrator_tick"]
        assert result["domains_scheduled"] == 0
        assert result["status"] == "completed"
        assert ticks == []
        assert recorded == []
    finally:
        await _cleanup_profile(search_index_id, crawl_profile_id)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_run_tick_creates_rag_namespace_once_per_worker(
    unique_id: str,
) -> None:
    search_index_id, crawl_profile_id = await _seed_profile(unique_id, max_domains_per_tick=1)
    orchestrator = _orchestrator(get_search_settings().crawl)
    created: list[str] = []
    rag_client = orchestrator._rag_client
    create_namespace = rag_client.create_namespace

    async def counting_create_namespace(
        name: str,
        description: str | None = None,
        *,
        provider: str | None = None,
    ):
        created.append(name)
        return await create_namespace(name, description, provider=provider)

    rag_client.create_namespace = counting_create_namespace
    try:
        await orchestrator.run_tick(
            crawl_profile_id=crawl_profile_id,
            trigger="manual",
            schedule_task_id=None,
        )
        await orchestrator.run_tick(
            crawl_profile_id=crawl_profile_id,
            trigger="manual",
            schedule_task_id=None,
        )
        assert created == [f"{search_index_id}:ns"]
    finally:
        await _cleanup_profile(search_index_id, crawl_profile_id)
