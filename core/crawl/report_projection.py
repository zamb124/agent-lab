"""Typed projections for crawl report read models."""

from __future__ import annotations

from datetime import date

from core.crawl.models import (
    CrawlEnrichedPage,
    CrawlPageFilterMetadata,
    CrawlUrlEnrichmentSnapshot,
)
from core.rag.models import RAGMetadata


def enrichment_snapshot_from_enriched_page(enriched_page: CrawlEnrichedPage) -> CrawlUrlEnrichmentSnapshot:
    filter_metadata = enriched_page.chunks[0].filter_metadata
    return CrawlUrlEnrichmentSnapshot(
        page_title=enriched_page.page_title,
        page_summary=enriched_page.page_summary,
        filter_metadata=filter_metadata,
    )


def _parse_iso_date_field(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = f"{token[:-1]}+00:00"
    try:
        from datetime import datetime

        return datetime.fromisoformat(token).date()
    except ValueError:
        if len(token) >= 10 and token[4] == "-" and token[7] == "-":
            year = int(token[0:4])
            month = int(token[5:7])
            day = int(token[8:10])
            return date(year, month, day)
        return None


def filter_metadata_from_rag_metadata(metadata: RAGMetadata) -> CrawlPageFilterMetadata | None:
    llm_enriched = metadata.get("llm_enriched")
    if llm_enriched is not True:
        return None
    content_type = metadata.get("content_type")
    primary_topic = metadata.get("primary_topic")
    topic_tags = metadata.get("topic_tags")
    language = metadata.get("language")
    audience = metadata.get("audience")
    if not isinstance(content_type, str):
        raise ValueError("RAG metadata content_type must be string when llm_enriched=true")
    if not isinstance(primary_topic, str):
        raise ValueError("RAG metadata primary_topic must be string when llm_enriched=true")
    if not isinstance(topic_tags, list):
        raise ValueError("RAG metadata topic_tags must be array when llm_enriched=true")
    if not isinstance(language, str):
        raise ValueError("RAG metadata language must be string when llm_enriched=true")
    if not isinstance(audience, str):
        raise ValueError("RAG metadata audience must be string when llm_enriched=true")
    category_path_raw = metadata.get("category_path")
    category_path: list[str] = []
    if category_path_raw is not None:
        if not isinstance(category_path_raw, list):
            raise ValueError("RAG metadata category_path must be array when present")
        for segment in category_path_raw:
            if not isinstance(segment, str):
                raise ValueError("RAG metadata category_path items must be strings")
            category_path.append(segment)
    date_precision = metadata.get("date_precision")
    freshness_relevance = metadata.get("freshness_relevance")
    payload: dict[str, object] = {
        "content_type": content_type,
        "date_published": _parse_iso_date_field(metadata.get("date_published")),
        "date_modified": _parse_iso_date_field(metadata.get("date_modified")),
        "date_precision": date_precision if isinstance(date_precision, str) else None,
        "primary_topic": primary_topic,
        "topic_tags": topic_tags,
        "category_path": category_path,
        "language": language,
        "audience": audience,
        "freshness_relevance": freshness_relevance if isinstance(freshness_relevance, str) else None,
    }
    return CrawlPageFilterMetadata.model_validate(payload)


def enrichment_snapshot_from_rag_metadata(metadata: RAGMetadata) -> CrawlUrlEnrichmentSnapshot | None:
    filter_metadata = filter_metadata_from_rag_metadata(metadata)
    if filter_metadata is None:
        return None
    page_title_raw = metadata.get("page_title")
    if not isinstance(page_title_raw, str) or not page_title_raw.strip():
        raise ValueError("RAG metadata page_title must be string when llm_enriched=true")
    page_summary_raw = metadata.get("page_summary")
    page_summary: str | None = None
    if isinstance(page_summary_raw, str) and page_summary_raw.strip():
        page_summary = page_summary_raw.strip()
    return CrawlUrlEnrichmentSnapshot(
        page_title=page_title_raw.strip(),
        page_summary=page_summary,
        filter_metadata=filter_metadata,
    )
