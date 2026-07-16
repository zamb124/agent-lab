"""Runet eval harness: golden set, arms, агрегация метрик (§17)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from apps.search.eval.metrics import (
    evaluate_query,
    untitled_rate,
    url_recall_at_k,
)
from apps.search.eval.models import (
    EvalArmRunConfig,
    EvalHarnessReport,
    EvalQuery,
    EvalQueryResult,
    EvalRetrievedUrl,
)
from core.search.index_study import (
    ChunkingArmId,
    get_chunking_arm,
    list_chunking_arms,
    list_index_study_arms,
)
from core.search.index_study.strategies import get_index_study_spec

SearchFn = Callable[[str, int], Awaitable[Sequence[EvalRetrievedUrl]]]
TitleFn = Callable[[Sequence[EvalRetrievedUrl]], Sequence[str]]

_DEFAULT_GOLDEN_PATH = Path(__file__).resolve().parent / "data" / "golden_queries.jsonl"


def load_golden_queries(path: Path | None = None) -> list[EvalQuery]:
    source = path or _DEFAULT_GOLDEN_PATH
    queries: list[EvalQuery] = []
    with source.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {source}:{line_number}") from exc
            queries.append(EvalQuery.model_validate(payload))
    return queries


def build_chunking_arm_config(arm_id: ChunkingArmId) -> EvalArmRunConfig:
    arm = get_chunking_arm(arm_id)
    return EvalArmRunConfig(
        arm_id=arm.arm_id,
        namespace_id=arm.shadow_namespace_suffix,
        arm_kind="chunking",
        notes=arm.purpose,
    )


def list_eval_arm_configs() -> list[EvalArmRunConfig]:
    arms: list[EvalArmRunConfig] = []
    for chunk_arm in list_chunking_arms():
        arms.append(
            EvalArmRunConfig(
                arm_id=chunk_arm.arm_id,
                namespace_id=chunk_arm.shadow_namespace_suffix,
                arm_kind="chunking",
                notes=chunk_arm.purpose,
            ),
        )
    for study_arm in list_index_study_arms():
        spec = get_index_study_spec(study_arm.strategy)
        arms.append(
            EvalArmRunConfig(
                arm_id=study_arm.arm_id,
                namespace_id=study_arm.shadow_namespace_suffix,
                arm_kind="index_study",
                notes=spec.description,
            ),
        )
    return arms


async def run_eval_harness(
    *,
    arm: EvalArmRunConfig,
    queries: Sequence[EvalQuery],
    search_fn: SearchFn,
    k: int = 10,
    title_fn: TitleFn | None = None,
) -> EvalHarnessReport:
    per_query: list[EvalQueryResult] = []
    url_recall_sum = 0.0
    ndcg_sum = 0.0
    mrr_sum = 0.0
    recall20_sum = 0.0
    dedup_sum = 0.0
    titles: list[str] = []
    by_type: dict[str, dict[str, list[float]]] = {}
    retrieved_cache: dict[str, list[EvalRetrievedUrl]] = {}

    for eval_query in queries:
        retrieved = list(await search_fn(eval_query.query, k))
        retrieved_cache[eval_query.query_id] = retrieved
        metrics = evaluate_query(eval_query, retrieved, k=k)
        per_query.append(
            EvalQueryResult(
                query_id=eval_query.query_id,
                query_type=eval_query.query_type,
                retrieved=retrieved,
                ideal_url_found=bool(metrics["url_recall"]),
                first_ideal_rank=metrics["first_ideal_rank"],  # type: ignore[arg-type]
                ndcg_at_k=float(metrics["ndcg"]),  # type: ignore[arg-type]
            ),
        )
        url_recall_sum += float(metrics["url_recall"])  # type: ignore[arg-type]
        ndcg_sum += float(metrics["ndcg"])  # type: ignore[arg-type]
        mrr_sum += float(metrics["mrr"])  # type: ignore[arg-type]
        recall20_sum += float(metrics["recall_20"])  # type: ignore[arg-type]
        dedup_sum += float(metrics["dedup_purity"])  # type: ignore[arg-type]

        bucket = by_type.setdefault(eval_query.query_type, {})
        bucket.setdefault("url_recall", []).append(float(metrics["url_recall"]))  # type: ignore[arg-type]
        bucket.setdefault("ndcg", []).append(float(metrics["ndcg"]))  # type: ignore[arg-type]

        if title_fn is not None:
            titles.extend(title_fn(retrieved))

    count = len(queries)
    rare_queries = [q for q in queries if q.query_type == "rare_term"]
    rare_recall: float | None = None
    if rare_queries:
        rare_hits = sum(
            1
            for rq in rare_queries
            if url_recall_at_k(
                retrieved_cache.get(rq.query_id, []),
                rq.relevances,
                k=k,
            )
        )
        rare_recall = rare_hits / len(rare_queries)

    aggregated_by_type = {
        query_type: {
            "url_recall_at_k": sum(values["url_recall"]) / len(values["url_recall"]),
            "ndcg_at_k": sum(values["ndcg"]) / len(values["ndcg"]),
        }
        for query_type, values in by_type.items()
        if values.get("url_recall")
    }

    return EvalHarnessReport(
        arm_id=arm.arm_id,
        namespace_id=arm.namespace_id,
        k=k,
        query_count=count,
        url_recall_at_k=url_recall_sum / count if count else 0.0,
        ndcg_at_k=ndcg_sum / count if count else 0.0,
        mrr_at_k=mrr_sum / count if count else 0.0,
        recall_at_20=recall20_sum / count if count else 0.0,
        untitled_rate=untitled_rate(titles) if titles else 0.0,
        url_dedup_purity_at_k=dedup_sum / count if count else 1.0,
        rare_term_url_recall_at_k=rare_recall,
        by_query_type=aggregated_by_type,
        per_query=per_query,
    )
