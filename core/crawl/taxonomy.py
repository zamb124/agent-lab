"""Taxonomy resolution and validation for crawl enrichment."""

from __future__ import annotations

from core.crawl.models import CrawlPageFilterMetadata
from core.search.index_models import SearchIndexCrawlTaxonomy

_TOPIC_TAG_ALIASES: dict[str, str] = {
    "bare_metal": "hardware",
    "category_path": "other",
    "comedy": "cinema",
    "domain": "directory",
    "author": "media",
    "primary_topic": "other",
    "topic_tags": "other",
    "filter_metadata": "other",
    "content_type": "other",
    "language": "other",
    "audience": "other",
}

_SCHEMA_FIELD_NAMES: frozenset[str] = frozenset(_TOPIC_TAG_ALIASES.keys())


def _resolve_topic_slug(token: str, allowed: set[str]) -> str:
    normalized = token.strip().lower()
    if not normalized:
        raise ValueError("taxonomy token must not be empty")
    if normalized in allowed:
        return normalized
    if normalized in _SCHEMA_FIELD_NAMES:
        mapped = _TOPIC_TAG_ALIASES[normalized]
        if mapped in allowed:
            return mapped
    alias = _TOPIC_TAG_ALIASES.get(normalized)
    if alias is not None and alias in allowed:
        return alias
    if "other" in allowed:
        return "other"
    raise ValueError(f"taxonomy token {token!r} cannot be mapped")


def _pick_category_path(
    category_path: list[str],
    primary_topic: str,
    taxonomy: SearchIndexCrawlTaxonomy,
) -> list[str]:
    if not taxonomy.category_paths:
        return []

    normalized = [segment.strip().lower() for segment in category_path if segment.strip()]
    allowed_paths = taxonomy.category_paths

    if normalized in allowed_paths:
        return normalized

    best_match: list[str] | None = None
    best_match_len = -1
    for allowed_path in allowed_paths:
        allowed_index = 0
        for segment in normalized:
            if allowed_index < len(allowed_path) and allowed_path[allowed_index] == segment:
                allowed_index += 1
        if allowed_index == len(allowed_path) and len(allowed_path) > best_match_len:
            best_match = allowed_path
            best_match_len = len(allowed_path)
    if best_match is not None:
        return best_match

    primary_only = [primary_topic]
    if primary_only in allowed_paths:
        return primary_only

    for allowed_path in allowed_paths:
        if allowed_path and allowed_path[0] == primary_topic:
            return allowed_path

    fallback = ["other"]
    if fallback in allowed_paths:
        return fallback

    raise ValueError("taxonomy category_paths has no fallback path")


def coerce_filter_metadata_for_taxonomy(
    filter_metadata: CrawlPageFilterMetadata,
    taxonomy: SearchIndexCrawlTaxonomy,
) -> CrawlPageFilterMetadata:
    allowed_primary_topics = set(taxonomy.primary_topics)
    allowed_topic_tags = set(taxonomy.topic_tags)

    primary_topic = _resolve_topic_slug(
        filter_metadata.primary_topic,
        allowed_primary_topics,
    )

    coerced_tags: list[str] = []
    for topic_tag in filter_metadata.topic_tags:
        resolved = _resolve_topic_slug(topic_tag, allowed_topic_tags)
        if resolved not in coerced_tags:
            coerced_tags.append(resolved)

    if primary_topic not in coerced_tags:
        coerced_tags.append(primary_topic)
    if len(coerced_tags) < 2 and "other" in allowed_topic_tags and "other" not in coerced_tags:
        coerced_tags.append("other")
    coerced_tags.sort()

    category_path = _pick_category_path(
        filter_metadata.category_path,
        primary_topic,
        taxonomy,
    )

    return filter_metadata.model_copy(
        update={
            "primary_topic": primary_topic,
            "topic_tags": coerced_tags[:5],
            "category_path": category_path,
        }
    )


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
