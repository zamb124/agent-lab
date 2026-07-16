"""Unit tests for live_passage_split (Phase 3 heading-split pipeline, §4.5.2)."""

from __future__ import annotations

from core.search.live_fetch import EvidencePassage, FetchedPage
from core.search.live_passage_split import split_page_to_passages, split_pages_to_passages


def _make_page(markdown: str, url: str = "https://example.com/page") -> FetchedPage:
    return FetchedPage(
        source_url=url,
        canonical_url=url,
        markdown=markdown,
        content_hash="deadbeef",
        fetch_transport="http",
        fetch_ms=200,
    )


def _make_failed_page(url: str = "https://example.com/fail") -> FetchedPage:
    return FetchedPage(
        source_url=url,
        canonical_url=url,
        markdown="",
        content_hash="",
        fetch_transport="failed",
        fetch_ms=100,
        error="timeout",
    )


def test_split_basic_sections() -> None:
    md = "# Article\n\nIntro.\n\n## Section A\n\nBody A.\n\n## Section B\n\nBody B.\n"
    page = _make_page(md)
    passages = split_page_to_passages(page, max_passage_tokens=200)
    titles = {p.section_title for p in passages}
    assert "Article" in titles
    assert "Section A" in titles
    assert "Section B" in titles


def test_split_word_cap() -> None:
    long_body = " ".join(f"word{i}" for i in range(1000))
    md = f"## Big Section\n\n{long_body}\n"
    page = _make_page(md)
    passages = split_page_to_passages(page, max_passage_tokens=50)
    for p in passages:
        if p.text:
            assert len(p.text.split()) <= 50


def test_split_failed_page_returns_empty() -> None:
    page = _make_failed_page()
    assert split_page_to_passages(page) == []


def test_split_empty_markdown_returns_empty() -> None:
    page = _make_page("   \n\n  ")
    assert split_page_to_passages(page) == []


def test_focus_hint_promotes_passage() -> None:
    md = "## Overview\n\nGeneral text.\n\n## Deployment\n\nDeploy text.\n"
    page = _make_page(md)
    passages = split_page_to_passages(page, focus_hint="Deployment")
    assert passages[0].section_title == "Deployment"


def test_max_passages_per_url_cap() -> None:
    sections = "\n".join(
        f"## Section {i}\n\nBody {i}." for i in range(100)
    )
    md = f"# Article\n\n{sections}\n"
    page = _make_page(md)
    passages = split_page_to_passages(page, max_passages_per_url=10)
    assert len(passages) <= 10


def test_evidence_passage_fields() -> None:
    md = "## My Section\n\nSome body text here.\n"
    page = _make_page(md, url="https://habr.com/article/123")
    passages = split_page_to_passages(page)
    passage = next(p for p in passages if p.section_title == "My Section")
    assert passage.source_url == "https://habr.com/article/123"
    assert isinstance(passage.heading_trail, list)
    assert passage.rerank_score is None


def test_split_pages_to_passages_global_cap() -> None:
    md = "\n".join(f"## Section {i}\n\nBody {i}." for i in range(50))
    pages = [_make_page(f"# Doc {i}\n\n{md}", url=f"https://example.com/{i}") for i in range(10)]
    passages = split_pages_to_passages(
        pages,
        max_passage_tokens=200,
        max_passages_per_url=20,
        max_passages_total=30,
    )
    assert len(passages) <= 30


def test_split_pages_skips_failed() -> None:
    ok_page = _make_page("## OK\n\nContent.", url="https://ok.com/")
    failed = _make_failed_page(url="https://fail.com/")
    passages = split_pages_to_passages([ok_page, failed])
    assert all(p.source_url == "https://ok.com/" for p in passages)


def test_char_start_monotone() -> None:
    md = "## A\n\nFirst.\n\n## B\n\nSecond.\n"
    page = _make_page(md)
    passages = split_page_to_passages(page)
    starts = [p.char_start for p in passages if p.char_start is not None]
    assert starts == sorted(starts)


def test_focus_hints_dict() -> None:
    md = "## Overview\n\nOverview text.\n\n## API\n\nAPI text.\n"
    page = _make_page(md, url="https://example.com/docs")
    passages = split_pages_to_passages(
        [page],
        focus_hints={"https://example.com/docs": "API"},
    )
    assert passages[0].section_title == "API"
