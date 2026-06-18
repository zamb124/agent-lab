"""Shared helpers for strict crawl E2E (real HTTP, TaskIQ, RAG, optional Humanitec LLM)."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.crawl.models import CrawlDomainSeed, SitemapEntry
from tests.search.conftest import make_search_index_slug

if TYPE_CHECKING:
    from httpx import AsyncClient

    from apps.search.container import SearchContainer

CRAWL_STRICT_ENRICHMENT_MODEL = "auto"


def require_crawl_humanitec_llm_live_gate() -> None:
    if os.getenv("CRAWL__E2E_HUMANITEC_LLM") != "1":
        import pytest

        pytest.skip("CRAWL__E2E_HUMANITEC_LLM=1 required for crawl Humanitec LLM live E2E")


@dataclass(frozen=True)
class CrawlStrictE2ESite:
    domain: str
    start_url: str
    search_query: str
    content_marker: str


CRAWL_STRICT_E2E_SITES: tuple[CrawlStrictE2ESite, ...] = (
    CrawlStrictE2ESite(
        domain="example.com",
        start_url="https://example.com/",
        search_query="Example Domain",
        content_marker="Example Domain",
    ),
    CrawlStrictE2ESite(
        domain="iana.org",
        start_url="https://www.iana.org/domains/reserved",
        search_query="Internet Assigned Numbers Authority reserved domains",
        content_marker="IANA",
    ),
)


async def create_search_index_and_profile(
    search_client: AsyncClient,
    search_container: SearchContainer,
    *,
    unique_id: str,
    llm_enrichment_enabled: bool = False,
) -> tuple[str, str]:
    search_index_id = make_search_index_slug(f"crawl_strict_{unique_id}")
    crawl_profile_id = f"cr_{search_index_id}"[:64]

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Crawl strict {unique_id}",
            "rag_namespace_id": f"{search_index_id}:ns",
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    create_profile = await search_client.post(
        "/search/api/v1/crawl/profiles",
        json={
            "crawl_profile_id": crawl_profile_id,
            "search_index_id": search_index_id,
            "seed_source": "manual",
            "max_urls_per_domain_per_tick": 1,
            "max_domains_per_tick": len(CRAWL_STRICT_E2E_SITES),
            "browser_fallback_enabled": False,
        },
    )
    assert create_profile.status_code == 201

    if llm_enrichment_enabled:
        await search_container.crawl_profile_repository.set_llm_enrichment(
            crawl_profile_id,
            llm_enrichment_enabled=True,
            enrichment_model=CRAWL_STRICT_ENRICHMENT_MODEL,
        )

    return search_index_id, crawl_profile_id


async def seed_strict_sites(
    search_container: SearchContainer,
    crawl_profile_id: str,
) -> None:
    seeds = [
        CrawlDomainSeed(domain=site.domain, category="strict_e2e", domain_rank=index + 1)
        for index, site in enumerate(CRAWL_STRICT_E2E_SITES)
    ]
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        seeds,
        next_crawl_after=datetime.now(UTC),
    )
    domain_page = await search_container.crawl_domain_repository.list_page(
        crawl_profile_id=crawl_profile_id,
        status=None,
        limit=50,
        offset=0,
    )
    domain_by_name = {domain.domain: domain for domain in domain_page.items}
    discovered_at = datetime.now(UTC)
    for site in CRAWL_STRICT_E2E_SITES:
        domain = domain_by_name[site.domain]
        _ = await search_container.crawl_url_repository.upsert_from_sitemap(
            domain.crawl_domain_id,
            [SitemapEntry(url=site.start_url)],
        )
        await search_container.crawl_domain_repository.mark_discovered(
            domain.crawl_domain_id,
            discovered_at,
        )


async def queue_crawl_orchestrator_tick(search_client: AsyncClient, crawl_profile_id: str) -> None:
    response = await search_client.post(
        "/search/api/v1/crawl/jobs",
        json={"crawl_profile_id": crawl_profile_id},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


async def queue_crawl_fetch_for_all_domains(
    search_client: AsyncClient,
    search_container: SearchContainer,
    crawl_profile_id: str,
) -> None:
    domain_page = await search_container.crawl_domain_repository.list_page(
        crawl_profile_id=crawl_profile_id,
        status=None,
        limit=50,
        offset=0,
    )
    for domain in domain_page.items:
        response = await search_client.post(
            f"/search/api/v1/crawl/domains/{domain.crawl_domain_id}/run",
            params={"crawl_profile_id": crawl_profile_id},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["status"] == "queued"
        assert payload["action"] in ("fetch", "discover")


def _indexed_count_from_status_counts(
    status_counts: list,
) -> int:
    for row in status_counts:
        if row.status == "indexed":
            return int(row.count)
    return 0


async def poll_indexed_url_count(
    search_client: AsyncClient,
    search_container: SearchContainer,
    *,
    crawl_profile_id: str,
    min_indexed: int,
    timeout_seconds: float,
    retry_ticks: int = 2,
) -> list[dict]:
    deadline = time.monotonic() + timeout_seconds
    last_total = 0
    ticks_sent = 0
    while time.monotonic() < deadline:
        status_counts = await search_container.crawl_url_repository.count_by_status_for_profile(
            crawl_profile_id
        )
        last_total = _indexed_count_from_status_counts(status_counts)
        if last_total >= min_indexed:
            page = await search_container.crawl_url_repository.list_page_for_profile(
                crawl_profile_id=crawl_profile_id,
                crawl_status="indexed",
                domain=None,
                limit=200,
                offset=0,
            )
            items = [item.model_dump(mode="json") for item in page.items]
            response = await search_client.get(
                "/search/api/v1/crawl/urls",
                params={
                    "crawl_profile_id": crawl_profile_id,
                    "crawl_status": "indexed",
                    "limit": 200,
                },
            )
            assert response.status_code == 200, response.text
            assert int(response.json()["total"]) >= min_indexed
            return items
        if ticks_sent < retry_ticks and time.monotonic() + 30.0 < deadline:
            await queue_crawl_fetch_for_all_domains(
                search_client,
                search_container,
                crawl_profile_id,
            )
            ticks_sent += 1
        await asyncio.sleep(2.0)
    status_summary = await search_container.crawl_url_repository.count_by_status_for_profile(
        crawl_profile_id
    )
    raise AssertionError(
        f"crawl strict E2E timeout: expected >={min_indexed} indexed urls, "
        f"got {last_total}; status_counts={status_summary!r}"
    )


async def poll_crawl_job_metric(
    search_client: AsyncClient,
    *,
    crawl_profile_id: str,
    metric: str,
    min_value: int,
    timeout_seconds: float,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_seen = 0
    while time.monotonic() < deadline:
        response = await search_client.get(
            "/search/api/v1/crawl/jobs",
            params={"crawl_profile_id": crawl_profile_id, "limit": 5},
        )
        assert response.status_code == 200
        jobs = response.json()["items"]
        if jobs:
            last_seen = int(jobs[0].get(metric, 0))
            if last_seen >= min_value:
                return jobs[0]
        await asyncio.sleep(2.0)
    raise AssertionError(
        f"crawl job metric timeout: {metric}>={min_value}, last={last_seen}"
    )


async def poll_index_search_hits(
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
            index_status = payload.get("providers", {}).get("index", {})
            if index_status.get("ok") is True and payload.get("results"):
                for item in payload["results"]:
                    url = item.get("url", "")
                    if url_domain not in url:
                        continue
                    snippet = item.get("snippet", "")
                    title = item.get("title", "")
                    haystack = f"{snippet} {title}".lower()
                    if content_marker.lower() in haystack:
                        return item
                    return item
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"index search timeout index={search_index_id!r} domain={url_domain!r} "
        f"marker={content_marker!r} last_status={last_status}"
    )


async def assert_layer1_urls_without_enrichment(indexed_urls: list[dict]) -> None:
    domains_seen: set[str] = set()
    for item in indexed_urls:
        assert item["crawl_status"] == "indexed"
        assert item["document_id"] is not None
        assert item["enriched_content_hash"] is None
        assert item["enrichment_model"] is None
        domains_seen.add(item["domain"])
    for site in CRAWL_STRICT_E2E_SITES:
        assert site.domain in domains_seen


async def enable_llm_enrichment_layer(
    search_container: SearchContainer,
    crawl_profile_id: str,
) -> int:
    await search_container.crawl_profile_repository.set_llm_enrichment(
        crawl_profile_id,
        llm_enrichment_enabled=True,
        enrichment_model=CRAWL_STRICT_ENRICHMENT_MODEL,
    )
    missing_count = await search_container.crawl_url_repository.requeue_indexed_missing_enrichment(
        crawl_profile_id
    )
    if missing_count < 1:
        raise AssertionError(f"expected indexed urls missing enrichment, got {missing_count}")
    backfill_job = await search_container.crawl_job_repository.start(
        crawl_profile_id,
        "manual",
        schedule_task_id=None,
    )
    enqueued = await search_container.crawl_orchestrator_service.enqueue_enrichment_backfill(
        crawl_profile_id,
        backfill_job.crawl_job_id,
        limit=missing_count,
    )
    if enqueued < 1:
        raise AssertionError(f"expected enrichment tasks enqueued, got {enqueued}")
    return enqueued


async def poll_enriched_urls(
    search_client: AsyncClient,
    *,
    crawl_profile_id: str,
    min_enriched: int,
    timeout_seconds: float,
) -> list[dict]:
    deadline = time.monotonic() + timeout_seconds
    last_count = 0
    while time.monotonic() < deadline:
        response = await search_client.get(
            "/search/api/v1/crawl/urls",
            params={"crawl_profile_id": crawl_profile_id, "limit": 200},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        enriched_items = [
            item
            for item in items
            if item.get("enriched_content_hash") and item.get("enrichment_model")
        ]
        last_count = len(enriched_items)
        if last_count >= min_enriched:
            return enriched_items
        await asyncio.sleep(3.0)
    raise AssertionError(
        f"crawl enrichment timeout: expected >={min_enriched} enriched urls, got {last_count}"
    )
