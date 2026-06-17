"""
Strict crawl E2E: multi-site list → HTTP parse/index → index search → LLM enrichment.

Без MockLLM, без monkeypatch, без прямых вызовов crawl_tasks:
- orchestrator tick через REST → TaskIQ search_worker
- fetch/enrich/ingest в worker-процессе
- RAG индексация через rag_worker + provider_litserve embeddings
- LLM enrichment через provider_litserve (порт 9022) при CRAWL__E2E_LITSERVE_LLM=1
"""

from __future__ import annotations

import pytest

from tests.search.integration.crawl_strict_e2e_support import (
    CRAWL_STRICT_E2E_SITES,
    CRAWL_STRICT_ENRICHMENT_MODEL,
    assert_layer1_urls_without_enrichment,
    create_search_index_and_profile,
    enable_llm_enrichment_layer,
    poll_enriched_urls,
    poll_index_search_hits,
    poll_indexed_url_count,
    queue_crawl_fetch_for_all_domains,
    require_crawl_llm_live_gate,
    seed_strict_sites,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_taskiq,
    pytest.mark.timeout(900, func_only=True),
]

MIN_INDEXED_URLS = len(CRAWL_STRICT_E2E_SITES)


@pytest.mark.asyncio
async def test_crawl_multi_site_layer1_parse_and_index_search_strict(
    search_client,
    search_worker,
    rag_worker,
    rag_service,
    provider_litserve_service,
    search_container,
    search_system_context,
    unique_id,
):
    """Слой 1: real HTTP fetch + RAG ingest + index search по списку сайтов."""
    _ = (
        search_worker,
        rag_worker,
        rag_service,
        provider_litserve_service,
        search_system_context,
    )
    search_index_id, crawl_profile_id = await create_search_index_and_profile(
        search_client,
        search_container,
        unique_id=unique_id,
        llm_enrichment_enabled=False,
    )
    await seed_strict_sites(search_container, crawl_profile_id)
    await queue_crawl_fetch_for_all_domains(search_client, search_container, crawl_profile_id)

    indexed_urls = await poll_indexed_url_count(
        search_client,
        search_container,
        crawl_profile_id=crawl_profile_id,
        min_indexed=MIN_INDEXED_URLS,
        timeout_seconds=360.0,
    )
    await assert_layer1_urls_without_enrichment(indexed_urls)

    for site in CRAWL_STRICT_E2E_SITES:
        hit = await poll_index_search_hits(
            search_client,
            search_index_id=search_index_id,
            query=site.search_query,
            url_domain=site.domain,
            content_marker=site.content_marker,
            timeout_seconds=180.0,
        )
        assert hit["search_index_id"] == search_index_id
        assert hit["source_type"] == "platform_index"
        assert site.domain in hit["url"]


@pytest.mark.asyncio
async def test_crawl_multi_site_two_layer_parse_search_then_llm_strict(
    search_client,
    search_worker,
    rag_worker,
    rag_service,
    provider_litserve_service,
    provider_litserve_crawl_llm_service,
    search_container,
    search_system_context,
    unique_id,
):
    """
    Полный двухслойный прогон:
    1) parse + index + search (без LLM)
    2) requeue → LLM enrichment → повторный index search с enriched metadata
    """
    require_crawl_llm_live_gate()
    _ = (
        search_worker,
        rag_worker,
        rag_service,
        provider_litserve_service,
        provider_litserve_crawl_llm_service,
        search_system_context,
    )

    search_index_id, crawl_profile_id = await create_search_index_and_profile(
        search_client,
        search_container,
        unique_id=unique_id,
        llm_enrichment_enabled=False,
    )
    await seed_strict_sites(search_container, crawl_profile_id)

    await queue_crawl_fetch_for_all_domains(search_client, search_container, crawl_profile_id)
    layer1_urls = await poll_indexed_url_count(
        search_client,
        search_container,
        crawl_profile_id=crawl_profile_id,
        min_indexed=MIN_INDEXED_URLS,
        timeout_seconds=360.0,
    )
    await assert_layer1_urls_without_enrichment(layer1_urls)

    for site in CRAWL_STRICT_E2E_SITES:
        hit = await poll_index_search_hits(
            search_client,
            search_index_id=search_index_id,
            query=site.search_query,
            url_domain=site.domain,
            content_marker=site.content_marker,
            timeout_seconds=120.0,
        )
        assert site.domain in hit["url"]

    requeued = await enable_llm_enrichment_layer(search_container, crawl_profile_id)
    assert requeued >= MIN_INDEXED_URLS

    await queue_crawl_fetch_for_all_domains(search_client, search_container, crawl_profile_id)

    enriched_urls = await poll_enriched_urls(
        search_client,
        crawl_profile_id=crawl_profile_id,
        min_enriched=MIN_INDEXED_URLS,
        timeout_seconds=600.0,
    )
    enriched_domains = {item["domain"] for item in enriched_urls}
    for site in CRAWL_STRICT_E2E_SITES:
        assert site.domain in enriched_domains

    for item in enriched_urls:
        assert item["crawl_status"] == "indexed"
        assert item["enrichment_model"] == CRAWL_STRICT_ENRICHMENT_MODEL
        assert item["enriched_content_hash"]
        assert item["enrichment_prompt_version"] == "v1"

    for site in CRAWL_STRICT_E2E_SITES:
        hit = await poll_index_search_hits(
            search_client,
            search_index_id=search_index_id,
            query=site.search_query,
            url_domain=site.domain,
            content_marker=site.content_marker,
            timeout_seconds=120.0,
        )
        assert site.domain in hit["url"]
