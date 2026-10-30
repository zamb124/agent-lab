"""Pure helpers for crawl LLM enrichment skip and content hashes."""

from __future__ import annotations

import hashlib

from core.crawl.models import CrawlEnrichedPage


def compute_enriched_content_hash(enriched_page: CrawlEnrichedPage) -> str:
    digest = hashlib.sha256(enriched_page.to_ingest_markdown().encode("utf-8")).hexdigest()
    return digest


def should_skip_crawl_url_after_fetch(
    *,
    llm_enrichment_enabled: bool,
    extract_hash: str,
    stored_extract_hash: str | None,
    stored_enriched_hash: str | None,
    stored_enrichment_prompt_version: str | None,
    current_prompt_version: str,
    document_id: str | None,
) -> bool:
    if document_id is None:
        return False
    if not llm_enrichment_enabled:
        if stored_extract_hash is None:
            return False
        return stored_extract_hash == extract_hash
    if stored_enrichment_prompt_version != current_prompt_version:
        return False
    if stored_extract_hash != extract_hash:
        return False
    if stored_enriched_hash is None:
        return False
    return True
