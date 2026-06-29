"""LLM enrichment of crawled pages via platform humanitec_llm free pool."""

from __future__ import annotations

import json
import time
from datetime import datetime

from apps.search.config import SearchCrawlEnrichmentConfig
from apps.search.services.crawl.taxonomy_registry import resolve_crawl_taxonomy
from core.ai.models import ResolvedAIModel
from core.ai.providers import AICapability
from core.ai.requirements import AIRequestRequirements, AISelection
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model
from core.clients.llm.client import LLMClient
from core.crawl.models import (
    CrawlDomain,
    CrawlEnrichedPage,
    CrawlEnrichedPageLLMOutput,
    CrawlFetchResult,
    CrawlProfile,
    CrawlStructuralSignals,
)
from core.crawl.taxonomy import (
    coerce_filter_metadata_for_taxonomy,
    validate_filter_metadata_against_taxonomy,
)
from core.search.index_models import SearchIndexCrawlTaxonomy
from core.tracing.operation_span import traced_operation
from core.types import JsonObject

_ENRICHMENT_SYSTEM_PROMPT = (
    "You extract structured crawl index records from web page markdown.\n"
    "Rules:\n"
    "1. Return ONLY JSON matching the schema. No prose outside JSON.\n"
    "2. Facts-only: every claim in body, summary, questions must be supported by markdown or structural_signals.\n"
    "3. Dates: use structural_signals first. If absent, extract ONLY from explicit bylines. Otherwise null — never guess from URL alone.\n"
    "4. Taxonomy: primary_topic, topic_tags, and category_path MUST be exact slugs/paths from the provided whitelist. "
    "Never put JSON field names (category_path, primary_topic, topic_tags) into topic_tags. "
    "If unsure, use primary_topic=other, topic_tags=[other, reference], category_path=[other].\n"
    "5. content_type: one of article, news, blog, product, documentation, tutorial, guide, faq, review, interview, opinion, press_release, research, case_study, changelog, support, catalog, landing, reference, wiki, tool, forum, legal, event, recipe, obituary, report, transcript, directory, portfolio, other; prefer structural_signals.content_type_hint.\n"
    "6. contextual_prefix: 50-120 tokens. Must mention page subject, site/domain context, and date if known.\n"
    "7. answerable_questions: 3-7 specific questions a user might search; must be answerable from body.\n"
    "8. body: normalized factual text; preserve numbers, proper nouns, definitions; remove nav/footer noise.\n"
    "9. Do not invent author, publisher, prices, or statistics.\n"
    "10. Language: page_title, page_summary, body, contextual_prefix, answerable_questions, and lexical_keywords "
    "MUST be written in the page primary language (filter_metadata.language, BCP-47). "
    "Never translate user-facing text to English unless the page itself is English. "
    "primary_topic, topic_tags, and category_path stay taxonomy slugs — do not translate slugs."
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

    def _document_language_prompt_line(self, structural_signals: CrawlStructuralSignals) -> str:
        page_language = structural_signals.language
        if page_language is not None:
            normalized = page_language.strip()
            if normalized:
                return (
                    "Document language (BCP-47 — use for filter_metadata.language and all user-facing fields): "
                    f"{normalized}\n"
                )
        return (
            "Document language: structural_signals.language is absent — infer primary language from markdown "
            "and HTML cues; set filter_metadata.language to a BCP-47 tag (e.g. ru, en, uk).\n"
        )

    def _build_user_prompt(
        self,
        *,
        markdown: str,
        url: str,
        domain: CrawlDomain,
        search_index_id: str,
        structural_signals: CrawlStructuralSignals,
        sitemap_lastmod: datetime | None,
        taxonomy: SearchIndexCrawlTaxonomy,
    ) -> str:
        sitemap_lastmod_text = sitemap_lastmod.isoformat() if sitemap_lastmod is not None else "null"
        signals_json = json.dumps(
            structural_signals.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        return (
            f"URL: {url}\n"
            f"Domain: {domain.domain}\n"
            f"Domain category (seed): {domain.category}\n"
            f"Sitemap lastmod: {sitemap_lastmod_text}\n"
            f"{self._document_language_prompt_line(structural_signals)}\n"
            "structural_signals (Layer 0, prefer over inference):\n"
            f"{signals_json}\n\n"
            f'Taxonomy whitelist for search_index "{search_index_id}":\n'
            f"primary_topics: {json.dumps(taxonomy.primary_topics, ensure_ascii=False)}\n"
            f"topic_tags: {json.dumps(taxonomy.topic_tags, ensure_ascii=False)}\n"
            f"category_paths: {json.dumps(taxonomy.category_paths, ensure_ascii=False)}\n\n"
            f"Markdown:\n{markdown}"
        )

    async def _invoke_enrichment_llm(
        self,
        *,
        markdown: str,
        url: str,
        profile: CrawlProfile,
        search_index_id: str,
        crawl_domain_id: str,
        domain: CrawlDomain,
        structural_signals: CrawlStructuralSignals,
        sitemap_lastmod: datetime | None,
    ) -> CrawlEnrichedPage:
        resolved = self._resolve_enrichment_llm(profile)
        enrichment_provider = resolved.provider
        enrichment_model_selected = resolved.model
        if enrichment_provider is None or enrichment_model_selected is None:
            raise ValueError("crawl enrichment: resolved LLM identity incomplete")
        prompt_version = self._enrichment_config.prompt_version
        taxonomy = resolve_crawl_taxonomy(search_index_id)
        truncated_markdown = self._truncate_markdown(markdown)
        user_prompt = self._build_user_prompt(
            markdown=truncated_markdown,
            url=url,
            domain=domain,
            search_index_id=search_index_id,
            structural_signals=structural_signals,
            sitemap_lastmod=sitemap_lastmod,
            taxonomy=taxonomy,
        )
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
            coerced_filter_metadata = coerce_filter_metadata_for_taxonomy(
                llm_output.chunks[0].filter_metadata,
                taxonomy,
            )
            llm_output = llm_output.model_copy(
                update={
                    "chunks": [
                        llm_output.chunks[0].model_copy(
                            update={"filter_metadata": coerced_filter_metadata}
                        )
                    ]
                }
            )
            validate_filter_metadata_against_taxonomy(
                llm_output.chunks[0].filter_metadata,
                taxonomy,
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
            return enriched_page

    async def enrich_page(
        self,
        *,
        fetched: CrawlFetchResult,
        profile: CrawlProfile,
        search_index_id: str,
        domain: CrawlDomain,
        crawl_domain_id: str,
        sitemap_lastmod: datetime | None = None,
    ) -> CrawlEnrichedPage:
        if not profile.llm_enrichment_enabled:
            raise ValueError("llm enrichment is disabled for crawl profile")
        return await self._invoke_enrichment_llm(
            markdown=fetched.markdown,
            url=fetched.url,
            profile=profile,
            search_index_id=search_index_id,
            crawl_domain_id=crawl_domain_id,
            domain=domain,
            structural_signals=fetched.structural_signals,
            sitemap_lastmod=sitemap_lastmod,
        )

    async def enrich_markdown(
        self,
        *,
        markdown: str,
        url: str,
        profile: CrawlProfile,
        search_index_id: str,
        domain: CrawlDomain,
        crawl_domain_id: str,
        structural_signals: CrawlStructuralSignals,
        sitemap_lastmod: datetime | None = None,
    ) -> CrawlEnrichedPage:
        if not profile.llm_enrichment_enabled:
            raise ValueError("llm enrichment is disabled for crawl profile")
        return await self._invoke_enrichment_llm(
            markdown=markdown,
            url=url,
            profile=profile,
            search_index_id=search_index_id,
            crawl_domain_id=crawl_domain_id,
            domain=domain,
            structural_signals=structural_signals,
            sitemap_lastmod=sitemap_lastmod,
        )
