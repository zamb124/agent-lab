"""Taxonomy resolution and validation for crawl enrichment."""

from __future__ import annotations

from core.crawl.models import CrawlPageFilterMetadata
from core.search.index_models import SearchIndexCrawlTaxonomy


def validate_filter_metadata_against_taxonomy(
    filter_metadata: CrawlPageFilterMetadata,
    taxonomy: SearchIndexCrawlTaxonomy,
) -> None:
    if filter_metadata.primary_topic not in taxonomy.primary_topics:
        raise ValueError(
            f"primary_topic {filter_metadata.primary_topic!r} not in taxonomy whitelist"
        )
    if len(filter_metadata.topic_tags) < 2:
        raise ValueError("topic_tags must contain at least 2 items")
    if len(filter_metadata.topic_tags) > 5:
        raise ValueError("topic_tags must contain at most 5 items")
    for topic_tag in filter_metadata.topic_tags:
        if topic_tag not in taxonomy.topic_tags:
            raise ValueError(f"topic_tag {topic_tag!r} not in taxonomy whitelist")
    if not taxonomy.category_paths:
        if filter_metadata.category_path:
            raise ValueError("category_path is not allowed when taxonomy category_paths is empty")
        return
    allowed = False
    for allowed_path in taxonomy.category_paths:
        if filter_metadata.category_path == allowed_path:
            allowed = True
            break
    if not allowed:
        raise ValueError(
            f"category_path {filter_metadata.category_path!r} not in taxonomy whitelist"
        )
