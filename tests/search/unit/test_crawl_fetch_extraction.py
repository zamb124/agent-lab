"""Crawl fetch extraction: metadata fallback and no-extractable semantics."""

from __future__ import annotations

import pytest

from apps.search.crawl.errors import CrawlExtractTooShortError, CrawlNoExtractableContentError
from apps.search.models import CrawlStructuralSignals
from apps.search.services.crawl.fetch_service import (
    _build_crawl_fetch_result,
    _extract_markdown_and_signals,
    _markdown_from_structural_signals,
)

pytestmark = pytest.mark.unit


def test_markdown_from_structural_signals_builds_title_and_description() -> None:
    signals = CrawlStructuralSignals(
        title="Game Title",
        description="Short game description for indexing.",
    )
    markdown = _markdown_from_structural_signals(signals)
    assert markdown is not None
    assert "# Game Title" in markdown
    assert "Short game description for indexing." in markdown


def test_extract_markdown_uses_metadata_fallback_when_body_empty() -> None:
    html = """<!DOCTYPE html>
<html><head>
<title>Meta Only</title>
<meta property="og:title" content="Meta Only"/>
<meta property="og:description" content="Enough metadata text for crawl indexing fallback validation."/>
</head><body></body></html>"""
    markdown, signals = _extract_markdown_and_signals(
        html.encode("utf-8"),
        "text/html",
        "https://example.com/game",
    )
    assert signals.title == "Meta Only"
    assert signals.description is not None
    assert "Enough metadata text" in (signals.description or "")


def test_extract_markdown_raises_no_extractable_content_when_empty() -> None:
    html = "<html><head></head><body><canvas></canvas></body></html>"
    with pytest.raises(CrawlNoExtractableContentError):
        _ = _extract_markdown_and_signals(
            html.encode("utf-8"),
            "text/html",
            "https://example.com/empty",
        )


def test_build_result_raises_extract_too_short_for_short_metadata_markdown() -> None:
    signals = CrawlStructuralSignals(title="Hi", description=None)
    markdown = _markdown_from_structural_signals(signals)
    assert markdown is not None
    with pytest.raises(CrawlExtractTooShortError):
        _ = _build_crawl_fetch_result(
            final_url="https://example.com/short",
            markdown=markdown,
            structural_signals=signals,
            min_extract_chars=50,
            fetch_transport="http",
        )
