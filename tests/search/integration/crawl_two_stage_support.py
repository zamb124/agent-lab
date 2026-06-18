"""Helpers for two-stage crawl pipeline integration tests."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.crawl.models import (
    CrawlDomainSeed,
    CrawlEnrichedChunk,
    CrawlEnrichedPage,
    CrawlProfileCreateRequest,
    SitemapEntry,
)
from core.search.index_models import SearchIndexCreateRequest
from tests.search.conftest import make_search_index_slug

if TYPE_CHECKING:
    from httpx import AsyncClient

    from apps.search.container import SearchContainer

REAL_CRAWL_DOMAIN = "example.com"
REAL_CRAWL_QUERY = "documentation examples"
REAL_CRAWL_MARKER = "Example Domain"


def deterministic_enriched_page(unique_id: str) -> CrawlEnrichedPage:
    marker = f"TWO_STAGE_ENRICH_{unique_id}"
    return CrawlEnrichedPage(
        page_summary=f"Structured summary {marker}",
        chunks=[
            CrawlEnrichedChunk(
                content=f"Enriched chunk body containing {marker} for search verification.",
                metadata_summary="Deterministic test enrichment chunk",
                hierarchy=["Introduction"],
            )
        ],
        enrichment_model="test-enrichment-model",
        enrichment_prompt_version="v1",
    )


async def setup_example_com_crawl(
    search_container: SearchContainer,
    *,
    unique_id: str,
    llm_enrichment_enabled: bool,
) -> tuple[str, str, str, str]:
    search_index_id = make_search_index_slug(f"two_stage_{unique_id}")
    crawl_profile_id = f"cr_{search_index_id}"[:64]
    rag_namespace_id = f"{search_index_id}:ns"

    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Two-stage crawl {unique_id}",
            rag_namespace_id=rag_namespace_id,
            rag_collection_id=search_index_id,
        )
    )
    await search_container.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            max_urls_per_domain_per_tick=1,
            browser_fallback_enabled=False,
        )
    )
    if llm_enrichment_enabled:
        await search_container.crawl_profile_repository.set_llm_enrichment(
            crawl_profile_id,
            llm_enrichment_enabled=True,
            enrichment_model="test-enrichment-model",
        )

    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=REAL_CRAWL_DOMAIN, category="docs", domain_rank=1)],
        next_crawl_after=datetime.now(UTC),
    )
    domain = (
        await search_container.crawl_domain_repository.list_due(
            crawl_profile_id,
            now=datetime.now(UTC),
            limit=1,
        )
    )[0]
    await search_container.crawl_url_repository.upsert_from_sitemap(
        domain.crawl_domain_id,
        [SitemapEntry(url=f"https://{REAL_CRAWL_DOMAIN}/")],
    )
    return search_index_id, crawl_profile_id, domain.crawl_domain_id, rag_namespace_id


async def run_layer1_fetch(
    search_container: SearchContainer,
    *,
    crawl_profile_id: str,
    crawl_domain_id: str,
) -> tuple[str, str]:
    job = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        "manual",
        schedule_task_id=None,
    )
    from apps.search_worker.tasks.crawl_tasks import crawl_fetch_url

    _ = await crawl_fetch_url(crawl_domain_id, job.crawl_job_id, crawl_profile_id, 1)
    job_after = await search_container.crawl_job_repository.get(job.crawl_job_id)
    assert job_after.urls_indexed >= 1
    url_page = await search_container.crawl_url_repository.list_page_for_profile(
        crawl_profile_id=crawl_profile_id,
        crawl_status="indexed",
        domain=REAL_CRAWL_DOMAIN,
        limit=1,
        offset=0,
    )
    assert url_page.total >= 1
    indexed_url = url_page.items[0]
    return job.crawl_job_id, indexed_url.crawl_url_id


async def run_layer2_enrich(
    search_container: SearchContainer,
    *,
    crawl_url_id: str,
    crawl_job_id: str,
    crawl_profile_id: str,
) -> None:
    from apps.search.services.system_context import build_search_system_context
    from core.context import clear_context, set_context

    trace_id = f"crawl:enrich:{crawl_url_id}"
    set_context(
        await build_search_system_context(
            trace_id=trace_id,
            company_repository=search_container.company_repository,
            subdomain_repository=search_container.subdomain_repository,
            user_repository=search_container.user_repository,
        )
    )
    try:
        await search_container.crawl_orchestrator_service.enrich_one_url(
            crawl_url_id,
            crawl_job_id,
            crawl_profile_id,
        )
    finally:
        clear_context()


async def poll_index_search(
    search_client: AsyncClient,
    *,
    search_index_id: str,
    query: str,
    url_domain: str,
    content_marker: str,
    timeout_seconds: float,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_status: int | None = None
    while time.monotonic() < deadline:
        response = await search_client.post(
            "/search/api/v1/search",
            json={
                "query": query,
                "limit": 5,
                "providers": ["index"],
                "index_ids": [search_index_id],
            },
        )
        last_status = response.status_code
        if response.status_code == 200:
            payload = response.json()
            if payload.get("results"):
                for item in payload["results"]:
                    url = item.get("url", "")
                    if url_domain not in url:
                        continue
                    haystack = f"{item.get('snippet', '')} {item.get('title', '')}".lower()
                    if content_marker.lower() in haystack:
                        return item
                    return item
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"index search timeout index={search_index_id!r} domain={url_domain!r} "
        f"marker={content_marker!r} last_status={last_status}"
    )


def install_enqueue_recorder(
    monkeypatch,
) -> list[tuple[object, ...]]:
    recorded: list[tuple[object, ...]] = []

    async def _record(task_name: str, *args: object, **kwargs: object) -> None:
        recorded.append((task_name, *args))

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _record,
    )
    return recorded
