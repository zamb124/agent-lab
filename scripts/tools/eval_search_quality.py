"""
Оценка качества платформенного поиска по golden-набору запросов.

Метрики: NDCG@10, MRR@10, Recall@50. Релевантность результата определяется
подстроками URL из golden-файла (grade 0-3). Скрипт бьёт в живой сервис search
(`POST /search/api/v1/search`) и пишет JSON-отчёт в ``reports/search_eval/``.

Запуск (сервисы подняты через ``make app``):

    uv run python -m scripts.tools.eval_search_quality
    uv run python -m scripts.tools.eval_search_quality --base-url http://localhost:8010 --label after_freshness

Сравнение с baseline: прогнать до и после изменений, сравнить отчёты по ``label``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx2
from pydantic import BaseModel, Field

DEFAULT_GOLDEN_PATH = Path("conf/search_eval/runet_golden.json")
DEFAULT_REPORTS_DIR = Path("reports/search_eval")
DEFAULT_BASE_URL = "http://localhost:8010"

NDCG_K = 10
MRR_K = 10
RECALL_K = 50


class GoldenRelevantUrl(BaseModel):
    url_substring: str = Field(..., min_length=1)
    grade: int = Field(..., ge=1, le=3)


class GoldenQuery(BaseModel):
    query: str = Field(..., min_length=1)
    recency_sensitive: bool = False
    relevant: list[GoldenRelevantUrl] = Field(..., min_length=1)


class GoldenSet(BaseModel):
    search_index_id: str = Field(..., min_length=1)
    description: str = ""
    queries: list[GoldenQuery] = Field(..., min_length=1)


class QueryEvalResult(BaseModel):
    query: str
    recency_sensitive: bool
    results_count: int
    ndcg_at_10: float
    mrr_at_10: float
    recall_at_50: float
    matched_urls: list[str]
    top_urls: list[str]
    error: str | None = None


class EvalReport(BaseModel):
    label: str
    base_url: str
    search_index_id: str
    generated_at: str
    queries_total: int
    queries_failed: int
    mean_ndcg_at_10: float
    mean_mrr_at_10: float
    mean_recall_at_50: float
    per_query: list[QueryEvalResult]


def _grade_for_url(url: str, relevant: list[GoldenRelevantUrl]) -> int:
    lowered = url.lower()
    best = 0
    for entry in relevant:
        if entry.url_substring.lower() in lowered and entry.grade > best:
            best = entry.grade
    return best


def _ndcg(grades: list[int], ideal_grades: list[int], k: int) -> float:
    def dcg(values: list[int]) -> float:
        return sum(
            (2**grade - 1) / math.log2(position + 2)
            for position, grade in enumerate(values[:k])
        )

    ideal = dcg(sorted(ideal_grades, reverse=True))
    if ideal == 0.0:
        return 0.0
    return dcg(grades) / ideal


def _mrr(grades: list[int], k: int) -> float:
    for position, grade in enumerate(grades[:k]):
        if grade > 0:
            return 1.0 / (position + 1)
    return 0.0


def _recall(grades: list[int], golden_query: GoldenQuery, urls: list[str], k: int) -> float:
    """Доля релевантных подстрок golden, покрытых первыми k результатами."""
    covered = 0
    for entry in golden_query.relevant:
        needle = entry.url_substring.lower()
        if any(needle in url.lower() for url in urls[:k]):
            covered += 1
    return covered / len(golden_query.relevant)


async def _run_query(
    client: httpx2.AsyncClient,
    base_url: str,
    golden_query: GoldenQuery,
    *,
    search_index_id: str,
    retrieve_limit: int,
) -> QueryEvalResult:
    body = {
        "query": golden_query.query,
        "limit": 25,
        "retrieve_limit": retrieve_limit,
        "providers": [search_index_id],
    }
    try:
        response = await client.post(f"{base_url}/search/api/v1/search", json=body)
        _ = response.raise_for_status()
        payload = response.json()
    except (httpx2.HTTPError, ValueError) as exc:
        return QueryEvalResult(
            query=golden_query.query,
            recency_sensitive=golden_query.recency_sensitive,
            results_count=0,
            ndcg_at_10=0.0,
            mrr_at_10=0.0,
            recall_at_50=0.0,
            matched_urls=[],
            top_urls=[],
            error=f"{type(exc).__name__}: {exc}",
        )
    results = payload.get("results", [])
    urls = [item["url"] for item in results if isinstance(item, dict) and "url" in item]
    grades = [_grade_for_url(url, golden_query.relevant) for url in urls]
    ideal_grades = [entry.grade for entry in golden_query.relevant]
    matched = [url for url, grade in zip(urls, grades) if grade > 0]
    return QueryEvalResult(
        query=golden_query.query,
        recency_sensitive=golden_query.recency_sensitive,
        results_count=len(urls),
        ndcg_at_10=round(_ndcg(grades, ideal_grades, NDCG_K), 4),
        mrr_at_10=round(_mrr(grades, MRR_K), 4),
        recall_at_50=round(_recall(grades, golden_query, urls, RECALL_K), 4),
        matched_urls=matched[:10],
        top_urls=urls[:10],
    )


async def run_eval(
    *,
    golden_path: Path,
    base_url: str,
    label: str,
    reports_dir: Path,
    retrieve_limit: int,
    timeout_seconds: float,
) -> EvalReport:
    golden = GoldenSet.model_validate(json.loads(golden_path.read_text(encoding="utf-8")))
    per_query: list[QueryEvalResult] = []
    async with httpx2.AsyncClient(timeout=timeout_seconds) as client:
        for golden_query in golden.queries:
            per_query.append(
                await _run_query(
                    client,
                    base_url,
                    golden_query,
                    search_index_id=golden.search_index_id,
                    retrieve_limit=retrieve_limit,
                )
            )
    succeeded = [item for item in per_query if item.error is None]
    failed_count = len(per_query) - len(succeeded)

    def _mean(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    report = EvalReport(
        label=label,
        base_url=base_url,
        search_index_id=golden.search_index_id,
        generated_at=datetime.now(UTC).isoformat(),
        queries_total=len(per_query),
        queries_failed=failed_count,
        mean_ndcg_at_10=_mean([item.ndcg_at_10 for item in succeeded]),
        mean_mrr_at_10=_mean([item.mrr_at_10 for item in succeeded]),
        mean_recall_at_50=_mean([item.recall_at_50 for item in succeeded]),
        per_query=per_query,
    )
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    report_path = reports_dir / f"{timestamp}_{label}.json"
    _ = report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"report: {report_path}")
    print(
        f"label={label} queries={report.queries_total} failed={report.queries_failed} "
        f"NDCG@10={report.mean_ndcg_at_10} MRR@10={report.mean_mrr_at_10} "
        f"Recall@50={report.mean_recall_at_50}"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Оценка качества платформенного поиска")
    _ = parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH)
    _ = parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL)
    _ = parser.add_argument("--label", type=str, default="baseline")
    _ = parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    _ = parser.add_argument("--retrieve-limit", type=int, default=100)
    _ = parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    report = asyncio.run(
        run_eval(
            golden_path=args.golden,
            base_url=args.base_url,
            label=args.label,
            reports_dir=args.reports_dir,
            retrieve_limit=args.retrieve_limit,
            timeout_seconds=args.timeout_seconds,
        )
    )
    if report.queries_failed == report.queries_total:
        print("all queries failed: сервис search недоступен или индекс пуст", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
