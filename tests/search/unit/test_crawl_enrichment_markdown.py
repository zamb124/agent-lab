"""Crawl enrichment markdown assembly."""

import pytest

from tests.search.unit.crawl_enrichment_fixtures import sample_enriched_page

pytestmark = pytest.mark.unit


def test_to_ingest_markdown_includes_context_questions_keywords():
    page = sample_enriched_page(
        page_title="Page title",
        page_summary="Page summary for search indexing.",
    )
    markdown = page.to_ingest_markdown()
    assert "Page title" in markdown
    assert "Page summary for search indexing." in markdown
    assert "### Topics" in markdown
    assert "### Content" in markdown
    assert "### Questions this page answers" in markdown
    assert "### Keywords" in markdown
    assert page.chunks[0].retrieval_augment.contextual_prefix in markdown
