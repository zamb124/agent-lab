"""Метрики runet eval harness (§17, §20.1)."""

from __future__ import annotations

import math
from collections.abc import Sequence

from apps.search.eval.models import EvalQuery, EvalRetrievedUrl, EvalUrlRelevance


def _grade_map(relevances: Sequence[EvalUrlRelevance]) -> dict[str, int]:
    out: dict[str, int] = {}
    for rel in relevances:
        canonical = rel.url.strip().lower().rstrip("/")
        out[canonical] = max(out.get(canonical, 0), rel.grade)
    return out


def _normalize_url(url: str) -> str:
    return url.strip().lower().rstrip("/")


def url_recall_at_k(
    retrieved: Sequence[EvalRetrievedUrl],
    relevances: Sequence[EvalUrlRelevance],
    *,
    k: int,
    min_grade: int = 2,
) -> bool:
    grades = _grade_map(relevances)
    for item in retrieved[:k]:
        grade = grades.get(_normalize_url(item.url), 0)
        if grade >= min_grade:
            return True
    return False


def first_relevant_rank(
    retrieved: Sequence[EvalRetrievedUrl],
    relevances: Sequence[EvalUrlRelevance],
    *,
    k: int,
    min_grade: int = 2,
) -> int | None:
    grades = _grade_map(relevances)
    for item in retrieved[:k]:
        if grades.get(_normalize_url(item.url), 0) >= min_grade:
            return item.rank
    return None


def mrr_at_k(
    retrieved: Sequence[EvalRetrievedUrl],
    relevances: Sequence[EvalUrlRelevance],
    *,
    k: int,
    min_grade: int = 2,
) -> float:
    rank = first_relevant_rank(retrieved, relevances, k=k, min_grade=min_grade)
    if rank is None:
        return 0.0
    return 1.0 / rank


def ndcg_at_k(
    retrieved: Sequence[EvalRetrievedUrl],
    relevances: Sequence[EvalUrlRelevance],
    *,
    k: int,
) -> float:
    grades = _grade_map(relevances)
    dcg = 0.0
    for index, item in enumerate(retrieved[:k], start=1):
        gain = float(grades.get(_normalize_url(item.url), 0))
        if gain <= 0:
            continue
        dcg += gain / math.log2(index + 1)

    ideal_gains = sorted(grades.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal_gains, start=1) if g > 0)
    if idcg <= 0:
        return 0.0
    return dcg / idcg


def recall_at_k(
    retrieved: Sequence[EvalRetrievedUrl],
    relevances: Sequence[EvalUrlRelevance],
    *,
    k: int,
    min_grade: int = 1,
) -> float:
    grades = _grade_map(relevances)
    relevant_urls = {url for url, grade in grades.items() if grade >= min_grade}
    if not relevant_urls:
        return 0.0
    found = {
        _normalize_url(item.url)
        for item in retrieved[:k]
        if grades.get(_normalize_url(item.url), 0) >= min_grade
    }
    return len(found) / len(relevant_urls)


def url_dedup_purity_at_k(retrieved: Sequence[EvalRetrievedUrl], *, k: int) -> float:
    slice_items = retrieved[:k]
    if not slice_items:
        return 1.0
    unique = len({_normalize_url(item.url) for item in slice_items})
    return unique / len(slice_items)


def untitled_rate(titles: Sequence[str]) -> float:
    if not titles:
        return 0.0
    untitled = sum(1 for title in titles if not title.strip() or title.strip().lower() == "untitled")
    return untitled / len(titles)


def evaluate_query(
    eval_query: EvalQuery,
    retrieved: Sequence[EvalRetrievedUrl],
    *,
    k: int,
) -> dict[str, float | bool | int | None]:
    return {
        "url_recall": url_recall_at_k(retrieved, eval_query.relevances, k=k),
        "ndcg": ndcg_at_k(retrieved, eval_query.relevances, k=k),
        "mrr": mrr_at_k(retrieved, eval_query.relevances, k=k),
        "recall_20": recall_at_k(retrieved, eval_query.relevances, k=20),
        "first_ideal_rank": first_relevant_rank(retrieved, eval_query.relevances, k=k),
        "dedup_purity": url_dedup_purity_at_k(retrieved, k=k),
    }
