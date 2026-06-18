"""Resolve crawl enrichment taxonomy for a search index."""

from __future__ import annotations

from apps.search.config import get_search_settings
from core.search.index_models import SearchIndexCrawlTaxonomy


def resolve_crawl_taxonomy(search_index_id: str) -> SearchIndexCrawlTaxonomy:
    slug = search_index_id.strip().lower()
    if not slug:
        raise ValueError("search_index_id is required")
    taxonomies = get_search_settings().crawl.taxonomies
    if slug not in taxonomies:
        raise ValueError(f"crawl taxonomy is not configured for search_index_id={slug}")
    return taxonomies[slug]
