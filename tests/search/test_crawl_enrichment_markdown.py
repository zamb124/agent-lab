"""Deterministic enriched markdown assembly."""

import pytest

from core.crawl.models import CrawlEnrichedChunk, CrawlEnrichedPage

pytestmark = pytest.mark.unit


def test_to_ingest_markdown_is_deterministic():
    page = CrawlEnrichedPage(
        page_summary="Page title",
        chunks=[
            CrawlEnrichedChunk(
                content="First paragraph body.",
                metadata_summary="Intro section",
                hierarchy=["Docs", "Getting started"],
            ),
            CrawlEnrichedChunk(
                content="Second paragraph body.",
                metadata_summary="Details section",
                hierarchy=[],
            ),
        ],
        enrichment_model="auto",
        enrichment_prompt_version="v1",
    )
    markdown = page.to_ingest_markdown()
    assert markdown == page.to_ingest_markdown()
    assert "# Page title" in markdown
    assert "## Docs > Getting started" in markdown
    assert "First paragraph body." in markdown
    assert "## Chunk 2" in markdown
    assert "Second paragraph body." in markdown
