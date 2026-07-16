"""Platform index search tool for flows."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from apps.search.container import get_search_container
from apps.search.eval.models import EvalRetrievedUrl
from core.clients.search_client import SearchClient
from core.clients.service_client import ServiceClientError
from core.models import StrictBaseModel
from core.search.models import MetaSearchRequest
from core.types import JsonObject, require_json_object


class IndexSearchToolArgs(StrictBaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    search_index_ids: list[str] = Field(..., min_length=1, max_length=5)
    limit: int = Field(default=8, ge=1, le=20)


async def _index_search_impl(
    query: str,
    search_index_ids: list[str],
    limit: int = 8,
) -> JsonObject:
    client = SearchClient()
    try:
        response = await client.search(
            MetaSearchRequest(
                query=query,
                limit=limit,
                providers=["index"],
                index_ids=search_index_ids,
            )
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "response": response.model_dump(mode="json")}


@tool(
    name="index_search",
    description="Hybrid search across platform RAG indexes by search_index_id slug",
    tags=["search", "index"],
    parameters_model=IndexSearchToolArgs,
)
async def index_search(
    query: str,
    search_index_ids: list[str],
    limit: int = 8,
) -> JsonObject:
    return await _index_search_impl(
        query=query,
        search_index_ids=search_index_ids,
        limit=limit,
    )


class RunetSearchToolArgs(StrictBaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)


@tool(
    name="runet_search",
    description="Hybrid search in the runet platform index",
    tags=["search", "runet"],
    parameters_model=RunetSearchToolArgs,
)
async def runet_search(query: str, limit: int = 8) -> JsonObject:
    return await _index_search_impl(
        query=query,
        search_index_ids=["runet"],
        limit=limit,
    )


class RunetDiscoverToolArgs(StrictBaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)


async def _runet_discover_impl(query: str, limit: int = 10) -> JsonObject:
    client = SearchClient()
    try:
        response = await client.search(
            MetaSearchRequest(
                query=query,
                limit=limit,
                providers=["index"],
                index_ids=["runet"],
                mode="quick",
            )
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    payload = require_json_object(response.model_dump(mode="json"), "RunetDiscoverResponse")
    return {
        "success": True,
        "is_discovery": True,
        "depth": 0,
        "response": payload,
    }


@tool(
    name="runet_discover",
    description=(
        "Discovery phase of runet search: returns top URLs with pointer-index metadata "
        "(title, snippet from page-card, section_title, salient_terms, heading_trail, "
        "indexed_at). Index-only, depth=0, no live web fetch. "
        "Use as the first step before runet_research or browser_page_markdown."
    ),
    tags=["search", "runet", "discovery"],
    parameters_model=RunetDiscoverToolArgs,
)
async def runet_discover(query: str, limit: int = 10) -> JsonObject:
    return await _runet_discover_impl(query=query, limit=limit)


class RunetResearchToolArgs(StrictBaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


async def _runet_research_impl(query: str, limit: int = 5) -> JsonObject:
    """Research pipeline: index → parallel fetch → split → rerank on-the-fly.

    Fetched page bodies are NEVER persisted to RAG storage.
    Returns top evidence passages with source citations.
    """
    container = get_search_container()
    orchestrator = container.research_orchestrator_service
    result = await orchestrator.research(query, index_ids=["runet"], limit=limit)
    summary = result.to_json_summary()
    return require_json_object({"success": True, **summary}, "runet_research result")


@tool(
    name="runet_research",
    description=(
        "Research mode: discovers top URLs in runet pointer-index, then fetches pages "
        "in parallel, splits by headings and reranks passages with a cross-encoder. "
        "Returns top evidence passages with source citations. "
        "Fetched content is NEVER stored in RAG — pipeline is fully in-memory. "
        "Use after runet_discover when you need full page content and grounded answers."
    ),
    tags=["search", "runet", "research"],
    parameters_model=RunetResearchToolArgs,
)
async def runet_research(query: str, limit: int = 5) -> JsonObject:
    return await _runet_research_impl(query=query, limit=limit)


# ---------------------------------------------------------------------------
# runet_eval_harness — live eval tool (§17, §20.1)
# ---------------------------------------------------------------------------


async def _discover_search_fn(query: str, k: int) -> list[EvalRetrievedUrl]:
    """Map runet_discover → EvalRetrievedUrl list for the eval harness."""
    result = await _runet_discover_impl(query=query, limit=k)
    if not result.get("success"):
        return []
    response = result.get("response")
    if not isinstance(response, dict):
        return []
    raw_results = response.get("results", [])
    if not isinstance(raw_results, list):
        return []
    out: list[EvalRetrievedUrl] = []
    for i, r in enumerate(raw_results[:k]):
        if not isinstance(r, dict):
            continue
        url = r.get("url", "")
        if not isinstance(url, str) or not url:
            continue
        score_raw = r.get("score", 0.0)
        score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0
        out.append(EvalRetrievedUrl(url=url, rank=i + 1, score=score))
    return out


class RunetEvalHarnessToolArgs(StrictBaseModel):
    arm: Literal["discover", "research"] = Field(
        default="discover",
        description="'discover' = pointer-index routing eval (fast); 'research' = live fetch + rerank eval (slow)",
    )
    limit_k: int = Field(default=10, ge=1, le=20, description="Evaluate recall / nDCG at top-K")
    max_queries: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Max golden queries to evaluate. Use ≤ 5 for research arm (each query fetches URLs live).",
    )
    query_types: list[str] | None = Field(
        default=None,
        description=(
            "Optional filter by query type(s): "
            "general, rare_term, paraphrase, short_ru, news, multi_hop, long_doc"
        ),
    )


async def _runet_eval_harness_impl(
    arm: str,
    limit_k: int,
    max_queries: int,
    query_types: list[str] | None,
) -> JsonObject:
    """Run the eval harness and return §20.1 metrics as a JSON summary."""
    from apps.search.eval.harness import load_golden_queries, run_eval_harness
    from apps.search.eval.models import EvalArmRunConfig

    if arm not in ("discover", "research"):
        return require_json_object(
            {"success": False, "error": f"unknown arm: {arm!r}"},
            "runet_eval_harness result",
        )

    queries = load_golden_queries()
    if query_types:
        allowed = set(query_types)
        queries = [q for q in queries if q.query_type in allowed]
    queries = queries[:max_queries]

    # Mutable accumulators for research-specific metrics (closures over lists are safe)
    res_fetch_success: list[int] = []
    res_fetch_failure: list[int] = []
    res_evidence_counts: list[int] = []
    res_statuses: list[str] = []

    async def _research_search_fn(query: str, k: int) -> list[EvalRetrievedUrl]:
        result = await _runet_research_impl(query=query, limit=min(k, 5))
        if result.get("success"):
            raw_ok = result.get("fetch_success")
            raw_fail = result.get("fetch_failure")
            raw_ev = result.get("evidence_count")
            res_fetch_success.append(int(raw_ok) if isinstance(raw_ok, (int, float, bool)) else 0)
            res_fetch_failure.append(int(raw_fail) if isinstance(raw_fail, (int, float, bool)) else 0)
            res_evidence_counts.append(int(raw_ev) if isinstance(raw_ev, (int, float, bool)) else 0)
            status_val = result.get("status")
            res_statuses.append(str(status_val) if isinstance(status_val, str) else "")
        sources_raw = result.get("sources") if result.get("success") else None
        if not isinstance(sources_raw, list):
            return []
        out: list[EvalRetrievedUrl] = []
        for i, s in enumerate(sources_raw[:k]):
            if not isinstance(s, dict):
                continue
            url = s.get("url")
            if not isinstance(url, str) or not url:
                continue
            score_raw = s.get("score")
            score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0
            out.append(EvalRetrievedUrl(url=url, rank=i + 1, score=score))
        return out

    search_fn = _discover_search_fn if arm == "discover" else _research_search_fn
    arm_config = EvalArmRunConfig(
        arm_id=arm,
        namespace_id="runet",
        arm_kind="chunking",
        notes=f"Live eval: {arm} arm, k={limit_k}",
    )
    report = await run_eval_harness(
        arm=arm_config,
        queries=queries,
        search_fn=search_fn,
        k=limit_k,
    )

    failures = [
        {
            "query_id": r.query_id,
            "query_type": r.query_type,
            "ndcg": round(r.ndcg_at_k, 3),
            "first_ideal_rank": r.first_ideal_rank,
        }
        for r in report.per_query
        if not r.ideal_url_found
    ]

    summary: dict[str, object] = {
        "success": True,
        "arm": arm,
        "query_count": report.query_count,
        "k": report.k,
        "url_recall_at_k": round(report.url_recall_at_k, 4),
        "ndcg_at_k": round(report.ndcg_at_k, 4),
        "mrr_at_k": round(report.mrr_at_k, 4),
        "recall_at_20": round(report.recall_at_20, 4),
        "url_dedup_purity_at_k": round(report.url_dedup_purity_at_k, 4),
        "rare_term_url_recall_at_k": (
            round(report.rare_term_url_recall_at_k, 4)
            if report.rare_term_url_recall_at_k is not None
            else None
        ),
        "by_query_type": report.by_query_type,
        "miss_count": len(failures),
        "misses": failures[:15],
    }

    if arm == "research" and res_fetch_success:
        total_fetched = sum(res_fetch_success) + sum(res_fetch_failure)
        summary["fetch_success_rate"] = (
            round(sum(res_fetch_success) / total_fetched, 4) if total_fetched > 0 else 0.0
        )
        summary["evidence_rate"] = round(
            sum(1 for c in res_evidence_counts if c > 0) / len(res_evidence_counts),
            4,
        )
        summary["avg_evidence_count"] = round(
            sum(res_evidence_counts) / len(res_evidence_counts),
            2,
        )
        status_counts: dict[str, int] = {}
        for s in res_statuses:
            status_counts[s] = status_counts.get(s, 0) + 1
        summary["status_distribution"] = status_counts

    return require_json_object(summary, "runet_eval_harness result")


@tool(
    name="runet_eval_harness",
    description=(
        "Run the runet search eval harness against the golden query set (§17, §20.1). "
        "arm='discover': fast pointer-index routing eval — url_recall@K, nDCG@K, MRR@K, "
        "rare_term_url_recall@K, dedup_purity; runs all golden queries. "
        "arm='research': live fetch + heading-split + rerank eval — adds fetch_success_rate, "
        "evidence_rate, status_distribution; use max_queries ≤ 5 (each query fetches URLs live). "
        "Returns metrics breakdown by query type and top misses for §20.4 diagnosis."
    ),
    tags=["search", "runet", "eval", "quality"],
    parameters_model=RunetEvalHarnessToolArgs,
)
async def runet_eval_harness(
    arm: Literal["discover", "research"] = "discover",
    limit_k: int = 10,
    max_queries: int = 20,
    query_types: list[str] | None = None,
) -> JsonObject:
    return await _runet_eval_harness_impl(
        arm=arm,
        limit_k=limit_k,
        max_queries=max_queries,
        query_types=query_types,
    )
