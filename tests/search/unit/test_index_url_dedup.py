"""Tests for runet index search URL dedup and multi-vector collapse."""

from __future__ import annotations

from apps.search.providers.index import (
    _collapse_multi_vector_by_document,
    _dedup_results_by_url,
)
from core.search import WebSearchResult


def _result(
    *,
    url: str,
    score: float,
    document_id: str | None = None,
    canonical_url: str | None = None,
    provider_rank: int = 1,
) -> WebSearchResult:
    return WebSearchResult(
        title=f"Title {url}",
        url=url,
        snippet="snippet",
        provider="index",
        provider_rank=provider_rank,
        score=score,
        document_id=document_id,
        canonical_url=canonical_url or url,
    )


def test_dedup_by_canonical_url_keeps_best_score() -> None:
    results = [
        _result(
            url="https://habr.com/ru/articles/1/",
            canonical_url="https://habr.com/ru/articles/1",
            score=0.4,
            provider_rank=1,
        ),
        _result(
            url="https://habr.com/ru/articles/1",
            canonical_url="https://habr.com/ru/articles/1",
            score=0.9,
            provider_rank=2,
        ),
        _result(url="https://vc.ru/devops/2", score=0.7, provider_rank=3),
    ]
    deduped = _dedup_results_by_url(results)
    assert len(deduped) == 2
    by_url = {item.canonical_url: item for item in deduped}
    assert by_url["https://habr.com/ru/articles/1"].score == 0.9


def test_collapse_multi_vector_by_document_id() -> None:
    results = [
        _result(
            url="https://habr.com/ru/articles/1#s1",
            document_id="runet:abc",
            score=0.5,
            provider_rank=1,
        ),
        _result(
            url="https://habr.com/ru/articles/1#s2",
            document_id="runet:abc",
            score=0.8,
            provider_rank=2,
        ),
    ]
    collapsed = _collapse_multi_vector_by_document(results)
    assert len(collapsed) == 1
    assert collapsed[0].score == 0.8
