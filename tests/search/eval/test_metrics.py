"""Tests for runet eval metrics."""

from __future__ import annotations

from apps.search.eval.metrics import (
    ndcg_at_k,
    url_dedup_purity_at_k,
    url_recall_at_k,
)
from apps.search.eval.models import EvalRetrievedUrl, EvalUrlRelevance


def test_url_recall_at_10() -> None:
    retrieved = [
        EvalRetrievedUrl(url="https://habr.com/a", rank=1, score=0.9),
        EvalRetrievedUrl(url="https://habr.com/b", rank=2, score=0.5),
    ]
    relevances = [EvalUrlRelevance(url="https://habr.com/b", grade=3)]
    assert url_recall_at_k(retrieved, relevances, k=10) is True
    assert url_recall_at_k(retrieved[:1], relevances, k=1) is False


def test_ndcg_perfect_ranking() -> None:
    retrieved = [
        EvalRetrievedUrl(url="https://habr.com/gold", rank=1, score=1.0),
        EvalRetrievedUrl(url="https://habr.com/noise", rank=2, score=0.1),
    ]
    relevances = [
        EvalUrlRelevance(url="https://habr.com/gold", grade=3),
        EvalUrlRelevance(url="https://habr.com/noise", grade=1),
    ]
    assert ndcg_at_k(retrieved, relevances, k=10) == 1.0


def test_url_dedup_purity() -> None:
    retrieved = [
        EvalRetrievedUrl(url="https://habr.com/1", rank=1, score=1.0),
        EvalRetrievedUrl(url="https://habr.com/1/", rank=2, score=0.9),
        EvalRetrievedUrl(url="https://vc.ru/2", rank=3, score=0.5),
    ]
    purity = url_dedup_purity_at_k(retrieved, k=3)
    assert purity < 1.0
