"""Unit tests for CrawlPageEnrichmentService LLM resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.search.config import SearchCrawlEnrichmentConfig
from apps.search.services.crawl.page_enrichment_service import CrawlPageEnrichmentService
from core.ai.models import ResolvedAIModel
from core.ai.providers import HUMANITEC_LLM_PROVIDER, AICapability
from core.ai.requirements import AIRequestRequirements, AISelection
from core.crawl.models import CrawlEnrichedChunk, CrawlEnrichedPageLLMOutput, CrawlProfile


def _profile(*, enrichment_model: str | None = None) -> CrawlProfile:
    now = datetime.now(UTC)
    return CrawlProfile(
        crawl_profile_id="cr_test",
        search_index_id="runet",
        enabled=True,
        seed_source="manual",
        refresh_interval_seconds=21600,
        max_urls_per_domain_per_tick=1,
        max_domains_per_tick=1,
        max_urls_per_batch=10,
        http_concurrency=2,
        browser_fallback_enabled=False,
        sitemap_stale_after_seconds=86400,
        llm_enrichment_enabled=True,
        enrichment_model=enrichment_model,
        created_at=now,
        updated_at=now,
    )


def test_resolve_enrichment_llm_uses_humanitec_free_pool() -> None:
    service = CrawlPageEnrichmentService(
        SearchCrawlEnrichmentConfig(provider=HUMANITEC_LLM_PROVIDER, model="auto"),
    )
    resolved_mock = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider=HUMANITEC_LLM_PROVIDER,
        model="auto",
        cost_origin="platform",
    )
    with patch(
        "apps.search.services.crawl.page_enrichment_service.resolve_ai_model",
        return_value=resolved_mock,
    ) as resolve_mock:
        resolved = service._resolve_enrichment_llm(_profile())

    resolve_mock.assert_called_once()
    call_kwargs = resolve_mock.call_args.kwargs
    requirements = call_kwargs["requirements"]
    assert isinstance(requirements, AIRequestRequirements)
    assert requirements.free_only is True
    assert requirements.structured_output is True
    assert requirements.json_mode is True
    selection = call_kwargs["selection"]
    assert isinstance(selection, AISelection)
    assert selection.provider == HUMANITEC_LLM_PROVIDER
    assert selection.model == "auto"
    assert call_kwargs["include_platform_default"] is False
    assert resolved.provider == HUMANITEC_LLM_PROVIDER


@pytest.mark.asyncio
async def test_invoke_enrichment_llm_disables_paid_fallback() -> None:
    service = CrawlPageEnrichmentService(
        SearchCrawlEnrichmentConfig(provider=HUMANITEC_LLM_PROVIDER, model="auto"),
    )
    resolved_mock = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider=HUMANITEC_LLM_PROVIDER,
        model="auto",
        cost_origin="platform",
    )
    llm_output = CrawlEnrichedPageLLMOutput(
        page_summary="summary",
        chunks=[
            CrawlEnrichedChunk(
                content="chunk body",
                metadata_summary="meta",
                hierarchy=["H1"],
            )
        ],
    )
    llm_client = MagicMock()
    llm_client.model = "openrouter:qwen/qwen-2.5-7b-instruct:free"
    llm_client.chat = AsyncMock(return_value=llm_output)

    with (
        patch.object(service, "_resolve_enrichment_llm", return_value=resolved_mock),
        patch(
            "apps.search.services.crawl.page_enrichment_service.create_llm_client_from_ai_model",
            return_value=llm_client,
        ) as create_client_mock,
    ):
        enriched = await service._invoke_enrichment_llm(
            markdown="# Title\n\nBody",
            url="https://example.com/",
            profile=_profile(),
            crawl_domain_id="dom-1",
        )

    create_client_mock.assert_called_once()
    assert create_client_mock.call_args.kwargs["allow_platform_paid_fallback"] is False
    assert enriched.enrichment_model == "openrouter:qwen/qwen-2.5-7b-instruct:free"
