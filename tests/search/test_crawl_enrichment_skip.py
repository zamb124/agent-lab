"""Skip matrix for crawl enrichment hashes."""

import pytest

from core.crawl.enrichment_skip import should_skip_crawl_url_after_fetch

pytestmark = pytest.mark.unit


def test_skip_when_extract_unchanged_without_enrichment():
    assert should_skip_crawl_url_after_fetch(
        llm_enrichment_enabled=False,
        extract_hash="abc",
        stored_extract_hash="abc",
        stored_enriched_hash=None,
        stored_enrichment_prompt_version=None,
        current_prompt_version="v1",
        document_id="doc-1",
    )


def test_no_skip_when_enrichment_enabled_but_no_enriched_hash():
    assert not should_skip_crawl_url_after_fetch(
        llm_enrichment_enabled=True,
        extract_hash="abc",
        stored_extract_hash="abc",
        stored_enriched_hash=None,
        stored_enrichment_prompt_version="v1",
        current_prompt_version="v1",
        document_id="doc-1",
    )


def test_skip_when_enrichment_hashes_and_prompt_match():
    assert should_skip_crawl_url_after_fetch(
        llm_enrichment_enabled=True,
        extract_hash="abc",
        stored_extract_hash="abc",
        stored_enriched_hash="enriched-1",
        stored_enrichment_prompt_version="v1",
        current_prompt_version="v1",
        document_id="doc-1",
    )


def test_no_skip_when_prompt_version_changed():
    assert not should_skip_crawl_url_after_fetch(
        llm_enrichment_enabled=True,
        extract_hash="abc",
        stored_extract_hash="abc",
        stored_enriched_hash="enriched-1",
        stored_enrichment_prompt_version="v1",
        current_prompt_version="v2",
        document_id="doc-1",
    )
