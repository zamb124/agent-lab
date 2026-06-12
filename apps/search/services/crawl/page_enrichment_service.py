"""LLM enrichment of crawled pages via provider_litserve chat."""

from __future__ import annotations

import time

from apps.search.config import SearchCrawlEnrichmentConfig
from core.ai.llm_config import LLMCallConfig
from core.ai.providers import PROVIDER_LITSERVE_CRAWL
from core.ai.runtime import create_llm_client_from_call_config
from core.clients.llm.client import LLMClient
from core.config import get_settings
from core.config.openai_v1_base_url import normalize_openai_v1_base_url
from core.crawl.models import (
    CrawlEnrichedPage,
    CrawlEnrichedPageLLMOutput,
    CrawlFetchResult,
    CrawlProfile,
)
from core.logging import get_logger
from core.rag.openai_http_contracts import PROVIDER_LITSERVE_PLACEHOLDER_BEARER
from core.tracing.operation_span import traced_operation

logger = get_logger(__name__)

_ENRICHMENT_SYSTEM_PROMPT = (
    "You structure web page markdown into semantic chunks for search indexing. "
    "Return only facts present in the source text. "
    "Do not invent entities, numbers, or claims. "
    "Each chunk must be self-contained and cite hierarchy headings from the page when available."
)


class CrawlPageEnrichmentService:
    def __init__(self, enrichment_config: SearchCrawlEnrichmentConfig) -> None:
        self._enrichment_config: SearchCrawlEnrichmentConfig = enrichment_config

    def _resolve_litserve_base_url(self) -> str:
        configured = self._enrichment_config.litserve_base_url
        if configured is not None and configured.strip():
            return normalize_openai_v1_base_url(configured.strip())
        return get_settings().provider_litserve.resolve_openai_v1_base_url()

    def _resolve_enrichment_model(self, profile: CrawlProfile) -> str:
        if profile.enrichment_model is not None and profile.enrichment_model.strip():
            return profile.enrichment_model.strip()
        return self._enrichment_config.default_model.strip()

    async def enrich_page(
        self,
        *,
        fetched: CrawlFetchResult,
        profile: CrawlProfile,
        crawl_domain_id: str,
    ) -> CrawlEnrichedPage:
        if not profile.llm_enrichment_enabled:
            raise ValueError("llm enrichment is disabled for crawl profile")
        markdown = fetched.markdown
        max_input_chars = self._enrichment_config.max_input_chars
        if len(markdown) > max_input_chars:
            raise ValueError(
                f"crawl markdown exceeds max_input_chars={max_input_chars}: url={fetched.url}"
            )
        enrichment_model = self._resolve_enrichment_model(profile)
        prompt_version = self._enrichment_config.prompt_version
        user_prompt = (
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
            "- chunks min 1\n"
            "- only facts from markdown\n"
            "- hierarchy reflects heading path when present\n\n"
            f"Markdown:\n{markdown}"
        )
        llm_client = create_llm_client_from_call_config(
            LLMCallConfig(
                provider=PROVIDER_LITSERVE_CRAWL,
                model=enrichment_model,
                base_url=self._resolve_litserve_base_url(),
                api_key=PROVIDER_LITSERVE_PLACEHOLDER_BEARER,
                max_tokens=4096,
                temperature=0.0,
            ),
        )
        if not isinstance(llm_client, LLMClient):
            raise RuntimeError("crawl page enrichment requires LLMClient")
        llm_client.timeout = self._enrichment_config.timeout_seconds
        started_at = time.monotonic()
        async with traced_operation(
            "crawl.enrich_page",
            extra_attributes={
                "crawl_domain_id": crawl_domain_id,
                "url": fetched.url,
                "enrichment_model": enrichment_model,
            },
        ) as span:
            llm_output = await llm_client.chat(
                [
                    {"role": "system", "content": _ENRICHMENT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=CrawlEnrichedPageLLMOutput,
            )
            enriched_page = CrawlEnrichedPage.from_llm_output(
                llm_output,
                enrichment_model=enrichment_model,
                enrichment_prompt_version=prompt_version,
            )
            latency_ms = int((time.monotonic() - started_at) * 1000)
            span.set_attributes(
                {
                    "chunk_count": len(enriched_page.chunks),
                    "llm_latency_ms": latency_ms,
                }
            )
            logger.info(
                "crawl enrichment completed url=%s model=%s chunks=%s latency_ms=%s",
                fetched.url,
                enrichment_model,
                len(enriched_page.chunks),
                latency_ms,
            )
            return enriched_page
