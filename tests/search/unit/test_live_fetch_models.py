"""Unit tests for FetchedPage and EvidencePassage dataclass contracts (§4.5.5)."""

from __future__ import annotations

from dataclasses import replace

from core.search.live_fetch import EvidencePassage, FetchedPage


def test_fetched_page_ok_http() -> None:
    page = FetchedPage(
        source_url="https://habr.com/article/1",
        canonical_url="https://habr.com/article/1",
        markdown="# Title\n\nBody text.",
        content_hash="abc123",
        fetch_transport="http",
        fetch_ms=300,
    )
    assert page.ok is True
    assert page.error is None


def test_fetched_page_ok_browser() -> None:
    page = FetchedPage(
        source_url="https://vc.ru/article/2",
        canonical_url="https://vc.ru/article/2",
        markdown="# Post",
        content_hash="def456",
        fetch_transport="browser",
        fetch_ms=5000,
    )
    assert page.ok is True


def test_fetched_page_failed() -> None:
    page = FetchedPage(
        source_url="https://example.com/broken",
        canonical_url="https://example.com/broken",
        markdown="",
        content_hash="",
        fetch_transport="failed",
        fetch_ms=8000,
        error="connection timeout",
    )
    assert page.ok is False
    assert page.error == "connection timeout"


def test_evidence_passage_defaults() -> None:
    ep = EvidencePassage(source_url="https://habr.com/article/3")
    assert ep.heading_trail == []
    assert ep.section_title == ""
    assert ep.text == ""
    assert ep.rerank_score is None
    assert ep.char_start is None


def test_evidence_passage_replace_score() -> None:
    ep = EvidencePassage(
        source_url="https://example.com/",
        section_title="Install",
        text="Run npm install.",
    )
    scored = replace(ep, rerank_score=0.95)
    assert scored.rerank_score == 0.95
    assert scored.source_url == ep.source_url
    assert ep.rerank_score is None  # original unchanged


def test_evidence_passage_heading_trail() -> None:
    ep = EvidencePassage(
        source_url="https://docs.example.com/",
        heading_trail=["Guide", "Installation"],
        section_title="Installation",
        text="Install the package.",
    )
    assert ep.heading_trail == ["Guide", "Installation"]
