"""Real HTTP crawl integration: sitemap discovery, fetch, RAG ingest, index search."""

import asyncio
from datetime import UTC, datetime

import pytest

from apps.search.config import get_search_settings
from apps.search_worker.tasks.crawl_tasks import crawl_discover_domain, crawl_fetch_url
from core.crawl.models import CrawlDomainSeed, CrawlProfileCreateRequest
from core.search.index_models import SearchIndexCreateRequest
from tests.search.conftest import make_search_index_slug

pytestmark = pytest.mark.timeout(180, func_only=True)

REAL_CRAWL_DOMAIN = "example.com"
REAL_CRAWL_QUERY = "documentation examples"


@pytest.mark.asyncio
async def test_discover_sitemap_example_com_real_http(crawl_search_container, search_system_context, unique_id):
    search_container = crawl_search_container
    from apps.search.services.crawl.sitemap_parser import discover_sitemap_urls

    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]

    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Crawl discover {unique_id}",
            rag_namespace_id=f"{search_index_id}:ns",
            rag_collection_id=search_index_id,
        )
    )
    await search_container.crawl_service.create_profile(
        CrawlProfileCreateRequest(
            crawl_profile_id=crawl_profile_id,
            search_index_id=search_index_id,
            seed_source="manual",
            max_urls_per_domain_per_tick=2,
            browser_fallback_enabled=False,
        )
    )
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=REAL_CRAWL_DOMAIN, category="docs", domain_rank=1)],
        next_crawl_after=datetime.now(UTC),
    )
    due = await search_container.crawl_domain_repository.list_due(
        crawl_profile_id,
        now=datetime.now(UTC),
        limit=1,
    )
    assert due
    domain_row = due[0]

    entries = await discover_sitemap_urls(
        domain_row.domain,
        timeout_seconds=get_search_settings().crawl.http_timeout_seconds,
        max_urls=get_search_settings().crawl.sitemap_max_urls_per_domain,
        max_sitemap_bytes=get_search_settings().crawl.sitemap_max_bytes,
    )
    assert entries
    assert any(entry.url.startswith("https://") for entry in entries)

    stats = await search_container.crawl_url_repository.upsert_from_sitemap(
        domain_row.crawl_domain_id,
        entries,
    )
    assert stats.inserted + stats.updated >= 1


@pytest.mark.asyncio
async def test_crawl_fetch_indexes_example_com_and_search_finds_content(
    search_client,
    rag_worker,
    provider_litserve_service,
    crawl_search_container,
    search_system_context,
    unique_id,
):
    search_container = crawl_search_container
    _ = rag_worker, provider_litserve_service
    search_index_id = make_search_index_slug(unique_id)
    crawl_profile_id = f"cr_{search_index_id}"[:64]
    rag_namespace_id = f"{search_index_id}:ns"

    await search_container.search_index_service.create(
        SearchIndexCreateRequest(
            search_index_id=search_index_id,
            display_name=f"Crawl index {unique_id}",
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
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain=REAL_CRAWL_DOMAIN, category="docs", domain_rank=1)],
        next_crawl_after=datetime.now(UTC),
    )
    due = await search_container.crawl_domain_repository.list_due(
        crawl_profile_id,
        now=datetime.now(UTC),
        limit=1,
    )
    assert due
    domain = due[0]
    job = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        "manual",
        schedule_task_id=None,
    )

    discover_result = await crawl_discover_domain(
        domain.crawl_domain_id,
        job.crawl_job_id,
        crawl_profile_id,
    )
    assert discover_result["status"] == "discovered"

    fetch_result = await crawl_fetch_url(
        domain.crawl_domain_id,
        job.crawl_job_id,
        crawl_profile_id,
        1,
    )
    assert fetch_result["status"] == "fetched"

    job_after = await search_container.crawl_job_repository.get(job.crawl_job_id)
    assert job_after.urls_indexed >= 1

    deadline = datetime.now(UTC).timestamp() + 90.0
    search_payload = None
    while datetime.now(UTC).timestamp() < deadline:
        response = await search_client.post(
            "/search/api/v1/search",
            json={
                "query": REAL_CRAWL_QUERY,
                "limit": 5,
                "providers": ["index"],
                "index_ids": [search_index_id],
            },
        )
        if response.status_code == 200 and response.json().get("results"):
            search_payload = response.json()
            break
        await asyncio.sleep(1.0)

    assert search_payload is not None
    assert search_payload["providers"]["index"]["ok"] is True
    top = search_payload["results"][0]
    assert top["search_index_id"] == search_index_id
    assert top["source_type"] == "platform_index"
    assert REAL_CRAWL_DOMAIN in top["url"]
    snippet = top.get("snippet", "")
    title = top.get("title", "")
    assert REAL_CRAWL_QUERY.lower() in snippet.lower() or REAL_CRAWL_QUERY.lower() in title.lower()
