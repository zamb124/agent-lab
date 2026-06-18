"""Shared crawl enrichment test fixtures."""

from __future__ import annotations

from core.crawl.models import (
    CrawlEnrichedChunk,
    CrawlEnrichedPage,
    CrawlPageFilterMetadata,
    CrawlPageRetrievalAugment,
)


def sample_filter_metadata(**overrides: object) -> CrawlPageFilterMetadata:
    payload = {
        "content_type": "documentation",
        "date_published": None,
        "date_modified": None,
        "date_precision": None,
        "primary_topic": "tech",
        "topic_tags": ["tech", "software"],
        "category_path": ["tech"],
        "language": "ru",
        "audience": "general",
        "freshness_relevance": "evergreen",
    }
    payload.update(overrides)
    return CrawlPageFilterMetadata.model_validate(payload)


def sample_retrieval_augment(**overrides: object) -> CrawlPageRetrievalAugment:
    payload = {
        "contextual_prefix": (
            "This page from example.com documents platform crawl enrichment behavior "
            "for search indexing on a technical documentation site."
        ),
        "answerable_questions": [
            "What is crawl enrichment?",
            "How does structured metadata help search?",
            "Which topics does this page cover?",
        ],
        "lexical_keywords": [
            "crawl",
            "enrichment",
            "metadata",
            "search",
            "indexing",
        ],
        "entity_names": ["Example Domain"],
    }
    payload.update(overrides)
    return CrawlPageRetrievalAugment.model_validate(payload)


def sample_enriched_chunk(**overrides: object) -> CrawlEnrichedChunk:
    chunk_payload = {
        "hierarchy": ["Introduction"],
        "body": "Example Domain is for use in illustrative examples in documents.",
        "filter_metadata": sample_filter_metadata(),
        "retrieval_augment": sample_retrieval_augment(),
    }
    chunk_payload.update(overrides)
    return CrawlEnrichedChunk.model_validate(chunk_payload)


def sample_enriched_page(
    *,
    page_title: str = "Example documentation page",
    page_summary: str = "Example page used for crawl enrichment tests.",
    enrichment_model: str = "auto",
    enrichment_prompt_version: str = "structured",
    marker: str | None = None,
) -> CrawlEnrichedPage:
    body = "Example Domain is for use in illustrative examples in documents."
    if marker is not None:
        body = f"{body} Marker: {marker}."
    chunk = sample_enriched_chunk(body=body)
    return CrawlEnrichedPage(
        page_title=page_title,
        page_summary=page_summary,
        chunks=[chunk],
        extraction_notes=[],
        enrichment_model=enrichment_model,
        enrichment_prompt_version=enrichment_prompt_version,
    )
