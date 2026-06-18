"""LLM enrichment of crawled pages via platform humanitec_llm free pool."""

from __future__ import annotations

import time

from apps.search.config import SearchCrawlEnrichmentConfig
from core.ai.models import ResolvedAIModel
from core.ai.providers import AICapability
from core.ai.requirements import AIRequestRequirements, AISelection
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model
from core.clients.llm.client import LLMClient
from core.crawl.models import (
    CrawlEnrichedPage,
    CrawlEnrichedPageLLMOutput,
    CrawlFetchResult,
    CrawlProfile,
)
from core.logging import get_logger
from core.tracing.operation_span import traced_operation
from core.types import JsonObject

logger = get_logger(__name__)

_ENRICHMENT_SYSTEM_PROMPT = (
    "You structure web page markdown into a single semantic chunk for search indexing. "
    "Return only facts present in the source text. "
    "Do not invent entities, numbers, or claims. "
    "The chunk must be self-contained and cite hierarchy headings from the page when available."
)

_CRAWL_ENRICHMENT_LLM_CONTEXT: JsonObject = {"profile": "off", "budget": "max"}


class CrawlPageEnrichmentService:
    def __init__(self, enrichment_config: SearchCrawlEnrichmentConfig) -> None:
        self._enrichment_config: SearchCrawlEnrichmentConfig = enrichment_config

    def _resolve_enrichment_model(self, profile: CrawlProfile) -> str:
        if profile.enrichment_model is not None and profile.enrichment_model.strip():
            return profile.enrichment_model.strip()
        return self._enrichment_config.model.strip()

    def _resolve_enrichment_provider(self) -> str:
        return self._enrichment_config.provider.strip()

    def _resolve_enrichment_llm(self, profile: CrawlProfile) -> ResolvedAIModel:
        provider = self._resolve_enrichment_provider()
        model = self._resolve_enrichment_model(profile)
        requirements = AIRequestRequirements(
            structured_output=True,
            json_mode=True,
            free_only=True,
        )
        selection = AISelection(provider=provider, model=model)
        resolved = resolve_ai_model(
            AICapability.LLM_CHAT,
            requirements=requirements,
            selection=selection,
            include_platform_default=False,
        )
        if resolved is None:
            raise ValueError(
                f"crawl enrichment: LLM route не разрешён provider={provider!r} model={model!r}"
            )
        if resolved.provider is None or not resolved.provider.strip():
            raise ValueError("crawl enrichment: resolved provider пуст")
        if resolved.model is None or not resolved.model.strip():
            raise ValueError("crawl enrichment: resolved model пуст")
        return resolved

    def _truncate_markdown(self, markdown: str) -> str:
        max_input_chars = self._enrichment_config.max_input_chars
        if len(markdown) <= max_input_chars:
            return markdown
        return markdown[:max_input_chars]

    def _build_user_prompt(self, markdown: str) -> str:
        return (
            "Extract structured page data from the markdown below.\n"
            "JSON schema:\n"
            "{\n"
            '  "page_summary": "string",\n'
            '  "chunks": [\n'
            "    {\n"
            '      "content": "string",\n'
            '      "metadata_summary": "string",\n'
            '      "hierarchy": ["string"]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- exactly one chunk in chunks array\n"
            "- page_summary is a concise page-level summary\n"
            "- metadata_summary describes what the chunk covers\n"
            "- only facts from markdown\n"
            "- hierarchy reflects heading path when present\n\n"
            f"Markdown:\n{markdown}"
        )

    async def _invoke_enrichment_llm(
        self,
        *,
        markdown: str,
        url: str,
        profile: CrawlProfile,
        crawl_domain_id: str,
    ) -> CrawlEnrichedPage:
        resolved = self._resolve_enrichment_llm(profile)
        enrichment_provider = resolved.provider
        enrichment_model_selected = resolved.model
        if enrichment_provider is None or enrichment_model_selected is None:
            raise ValueError("crawl enrichment: resolved LLM identity incomplete")
        prompt_version = self._enrichment_config.prompt_version
        truncated_markdown = self._truncate_markdown(markdown)
        user_prompt = self._build_user_prompt(truncated_markdown)
        llm_client = create_llm_client_from_ai_model(
            resolved,
            temperature=0.0,
            max_tokens=4096,
            allow_platform_paid_fallback=False,
        )
        if not isinstance(llm_client, LLMClient):
            raise RuntimeError("crawl page enrichment requires LLMClient")
        llm_client.timeout = int(self._enrichment_config.timeout_seconds)
        llm_client.first_token_timeout = self._enrichment_config.timeout_seconds
        started_at = time.monotonic()
        async with traced_operation(
            "crawl.enrich_page",
            extra_attributes={
                "crawl_domain_id": crawl_domain_id,
                "url": url,
                "enrichment_provider": enrichment_provider,
                "enrichment_model": enrichment_model_selected,
                "enrichment_cost_origin": resolved.cost_origin,
            },
        ) as span:
            llm_output = await llm_client.chat(
                [
                    {"role": "system", "content": _ENRICHMENT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=CrawlEnrichedPageLLMOutput,
                llm_context=_CRAWL_ENRICHMENT_LLM_CONTEXT,
            )
            used_model = llm_client.model.strip()
            if not used_model:
                raise ValueError("crawl enrichment: LLM model пуст после вызова")
            enriched_page = CrawlEnrichedPage.from_llm_output(
                llm_output,
                enrichment_model=used_model,
                enrichment_prompt_version=prompt_version,
            )
            latency_ms = int((time.monotonic() - started_at) * 1000)
            span.set_attributes(
                {
                    "chunk_count": len(enriched_page.chunks),
                    "llm_latency_ms": latency_ms,
                    "llm_model_used": used_model,
                }
            )
            logger.info(
                "crawl enrichment completed url=%s provider=%s model=%s chunks=%s latency_ms=%s",
                url,
                enrichment_provider,
                used_model,
                len(enriched_page.chunks),
                latency_ms,
            )
            return enriched_page

    async def enrich_page(
        self,
        *,
        fetched: CrawlFetchResult,
        profile: CrawlProfile,
        crawl_domain_id: str,
    ) -> CrawlEnrichedPage:
        if not profile.llm_enrichment_enabled:
            raise ValueError("llm enrichment is disabled for crawl profile")
        return await self._invoke_enrichment_llm(
            markdown=fetched.markdown,
            url=fetched.url,
            profile=profile,
            crawl_domain_id=crawl_domain_id,
        )

    async def enrich_markdown(
        self,
        *,
        markdown: str,
        url: str,
        profile: CrawlProfile,
        crawl_domain_id: str,
    ) -> CrawlEnrichedPage:
        if not profile.llm_enrichment_enabled:
            raise ValueError("llm enrichment is disabled for crawl profile")
        return await self._invoke_enrichment_llm(
            markdown=markdown,
            url=url,
            profile=profile,
            crawl_domain_id=crawl_domain_id,
        )
