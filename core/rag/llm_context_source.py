"""RAG-источник для платформенного LLM context layer."""

from __future__ import annotations

import math

from core.clients.rag_client import RagClient
from core.config import get_settings
from core.llm_context import LLMContextBlock, LLMContextSourceRequest
from core.llm_context.retrieval_rag_bridge import rag_search_options_override_from_retrieval
from core.rag.models import RAGMetadataFilter, RAGSearchOptions, RAGSearchResult
from core.rag.rag_http_namespace_search import merge_search_request_options
from core.rag.rag_resource_bind import RagResourceBindParams
from core.rag.search_options_resolver import resolve_platform_search_options
from core.types import JsonObject, JsonValue, require_json_object


class RAGLLMContextSource:
    """Собирает результаты RAG-поиска как candidate-блоки ``LLMContextBlock``."""

    def __init__(
        self,
        *,
        bind: RagResourceBindParams,
        rag_client: RagClient | None = None,
        name: str | None = None,
        filters: RAGMetadataFilter | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.bind: RagResourceBindParams = bind
        self.rag_client: RagClient = rag_client if rag_client is not None else RagClient()
        self.name: str = _source_name(name or f"rag.{self.bind.namespace}")
        self.filters: RAGMetadataFilter | None = dict(filters) if filters else None
        self.timeout: float = timeout

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        query = str(request.query or "").strip()
        if request.policy.retrieval.mode == "off" or not query:
            return []

        search_options = merge_search_request_options(
            self.bind.search_options,
            _search_options_from_policy(request),
        )
        if search_options is None:
            search_options = RAGSearchOptions()
        merged_filters = _merge_filters(self.filters, self.bind)
        response = await self.rag_client.search(
            namespace_id=self.bind.namespace,
            query=query,
            limit=request.policy.retrieval.top_k,
            filters=merged_filters,
            provider=self.bind.provider,
            channels=search_options.channels,
            rrf_k=search_options.rrf_k,
            per_channel_top_k=search_options.per_channel_top_k,
            rerank=search_options.rerank,
            rerank_max_candidates=search_options.rerank_max_candidates,
            retrieval=search_options.retrieval,
            freshness_weight=search_options.freshness_weight,
            freshness_half_life_days=search_options.freshness_half_life_days,
            timeout=self.timeout,
        )
        results = _coerce_results(response)
        return [
            _result_to_block(result, rank=index + 1, source_name=self.name)
            for index, result in enumerate(results)
        ]


def _merge_filters(
    filters: RAGMetadataFilter | None,
    bind: RagResourceBindParams,
) -> RAGMetadataFilter | None:
    if not bind.filters:
        return filters
    merged = dict(bind.filters)
    if filters:
        merged.update(filters)
    return merged


def _search_options_from_policy(request: LLMContextSourceRequest) -> RAGSearchOptions:
    policy_override = rag_search_options_override_from_retrieval(request.policy.retrieval)
    return resolve_platform_search_options(
        settings=get_settings(),
        overrides=policy_override,
    )


def _coerce_results(response: JsonObject) -> list[RAGSearchResult]:
    raw_results = response.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("RAG LLM context source expected response.results list")
    return [
        item if isinstance(item, RAGSearchResult) else RAGSearchResult.model_validate(
            require_json_object(item, "RAG LLM context result")
        )
        for item in raw_results
    ]


def _result_to_block(
    result: RAGSearchResult,
    *,
    rank: int,
    source_name: str,
) -> LLMContextBlock:
    score = _clamp_score(result.score)
    namespace = result.namespace.strip()
    document_id = result.document_id.strip()
    stable_key = _stable_key(result)
    provenance = {
        **dict(result.provenance),
        "source": source_name,
        "namespace": namespace,
        "document_id": document_id,
        "document_name": result.document_name,
        "chunk_id": result.chunk_id,
        "rank": rank,
        "score": result.score,
    }
    return LLMContextBlock(
        kind="rag",
        budget_scope="rag",
        role="system",
        content=_format_result_content(result, rank=rank, score=score),
        stable_key=stable_key,
        priority=max(0, 100 - rank),
        score=score,
        provenance=provenance,
    )


def _format_result_content(
    result: RAGSearchResult,
    *,
    rank: int,
    score: float | None,
) -> str:
    score_text = "n/a" if score is None else f"{score:.4f}"
    title = result.document_name or result.document_id
    return (
        f"[RAG context #{rank} namespace={result.namespace} "
        f"document={title} score={score_text}]\n{result.content}"
    )


def _stable_key(result: RAGSearchResult) -> str:
    chunk_id = result.chunk_id.strip()
    if not chunk_id:
        chunk_id = str(result.chunk_index)
    return f"rag:{result.namespace}:{result.document_id}:{chunk_id}"


def _clamp_score(value: JsonValue) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        score = float(value)
    elif isinstance(value, str):
        try:
            score = float(value)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(score):
        return None
    return min(1.0, max(0.0, score))


def _source_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "_" for ch in name)
    safe = safe.strip("._-")
    if not safe:
        return "rag.source"
    return safe


__all__ = ["RAGLLMContextSource"]
