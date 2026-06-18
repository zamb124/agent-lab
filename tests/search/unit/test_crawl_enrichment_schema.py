"""Crawl enrichment schema validation."""

import pytest
from pydantic import ValidationError

from core.crawl.models import CrawlEnrichedPage, CrawlEnrichedPageLLMOutput
from core.crawl.taxonomy import validate_filter_metadata_against_taxonomy
from core.search.index_models import SearchIndexCrawlTaxonomy
from tests.search.unit.crawl_enrichment_fixtures import (
    sample_enriched_chunk,
    sample_enriched_page,
    sample_filter_metadata,
)

pytestmark = pytest.mark.unit


def test_crawl_enriched_page_from_valid_json():
    payload = CrawlEnrichedPageLLMOutput(
        page_title="Example documentation page",
        page_summary="Example page used in documentation.",
        chunks=[sample_enriched_chunk()],
    )
    page = CrawlEnrichedPage.from_llm_output(
        payload,
        enrichment_model="auto",
        enrichment_prompt_version="structured",
    )
    assert page.page_title == "Example documentation page"
    assert len(page.chunks) == 1


def test_crawl_enriched_page_rejects_empty_chunks():
    with pytest.raises(ValidationError):
        _ = CrawlEnrichedPage(
            page_title="Title",
            page_summary="Summary",
            chunks=[],
            extraction_notes=[],
            enrichment_model="auto",
            enrichment_prompt_version="structured",
        )


def test_crawl_enriched_page_llm_output_rejects_multiple_chunks():
    chunk = sample_enriched_chunk()
    with pytest.raises(ValidationError):
        _ = CrawlEnrichedPageLLMOutput(
            page_title="Example documentation page",
            page_summary="Example page used in documentation.",
            chunks=[chunk, chunk],
        )


def test_validate_filter_metadata_against_taxonomy_rejects_unknown_topic():
    taxonomy = SearchIndexCrawlTaxonomy(
        primary_topics=["tech", "other"],
        topic_tags=["tech", "software", "other"],
        category_paths=[["tech"]],
    )
    filter_metadata = sample_filter_metadata(primary_topic="finance", topic_tags=["finance", "other"])
    with pytest.raises(ValueError, match="primary_topic"):
        validate_filter_metadata_against_taxonomy(filter_metadata, taxonomy)


def test_sample_enriched_page_builds():
    page = sample_enriched_page(marker="schema-test")
    markdown = page.to_ingest_markdown()
    assert "Example documentation page" in markdown
    assert "Questions this page answers" in markdown
    assert "Keywords" in markdown
