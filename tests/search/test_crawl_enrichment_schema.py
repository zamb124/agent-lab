"""Crawl enrichment schema validation."""

import pytest
from pydantic import ValidationError

from core.crawl.models import CrawlEnrichedChunk, CrawlEnrichedPage, CrawlEnrichedPageLLMOutput

pytestmark = pytest.mark.unit


def test_crawl_enriched_page_from_valid_json():
    payload = CrawlEnrichedPageLLMOutput(
        page_summary="Example documentation page",
        chunks=[
            CrawlEnrichedChunk(
                content="Example Domain is for use in illustrative examples.",
                metadata_summary="Purpose of example.com",
                hierarchy=["Introduction"],
            )
        ],
    )
    page = CrawlEnrichedPage.from_llm_output(
        payload,
        enrichment_model="qwen/qwen2.5-1.5b-instruct-crawl",
        enrichment_prompt_version="v1",
    )
    assert page.page_summary == "Example documentation page"
    assert len(page.chunks) == 1


def test_crawl_enriched_page_rejects_empty_chunks():
    with pytest.raises(ValidationError):
        _ = CrawlEnrichedPage(
            page_summary="Summary",
            chunks=[],
            enrichment_model="qwen/qwen2.5-1.5b-instruct-crawl",
            enrichment_prompt_version="v1",
        )
