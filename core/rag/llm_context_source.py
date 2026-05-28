"""RAG-источник для платформенного LLM context layer."""

from __future__ import annotations

import hashlib
import math

from core.llm_context import LLMContextBlock, LLMContextSourceRequest
from core.rag.models import RAGMetadataFilter, RAGSearchOptions, RAGSearchResult
from core.rag.rag_resource_bind import RagResourceBindParams
from core.rag.repository import RAGRepository
from core.rag_indexing_schema import SearchChannelsDefaults
from core.types import JsonObject, JsonValue, require_json_object


class RAGLLMContextSource:
    """Собирает результаты RAG-поиска как candidate-блоки ``LLMContextBlock``."""

    def __init__(
        self,
        *,
        repository: RAGRepository,
        bind: RagResourceBindParams,
        name: str | None = None,
        filters: RAGMetadataFilter | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.repository: RAGRepository = repository
        self.bind: RagResourceBindParams = bind
        self.name: str = _source_name(name or f"rag.{self.bind.namespace}")
        self.filters: RAGMetadataFilter | None = dict(filters) if filters else None
        self.timeout: float = timeout

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        query = str(request.query or "").strip()
        if request.policy.retrieval.mode == "off" or not query:
            return []

        response = await self.repository.search_namespace(
            query=query,
            limit=request.policy.retrieval.top_k,
            filters=self.filters,
            bind=self.bind,
            search_options=_search_options_from_policy(request),
            timeout=self.timeout,
        )
        results = _coerce_results(response)
        return [
            _result_to_block(result, rank=index + 1, source_name=self.name)
            for index, result in enumerate(results)
        ]


def _search_options_from_policy(request: LLMContextSourceRequest) -> RAGSearchOptions:
    retrieval = request.policy.retrieval
    return RAGSearchOptions(
        channels=_channels_from_retrieval_mode(retrieval.mode),
        rerank=retrieval.rerank,
        retrieval=retrieval.mode != "off",
    )


def _channels_from_retrieval_mode(mode: str) -> SearchChannelsDefaults:
    if mode == "hybrid":
        return SearchChannelsDefaults(semantic=True, lexical=True)
    if mode == "lexical":
        return SearchChannelsDefaults(semantic=False, lexical=True)
    return SearchChannelsDefaults(semantic=True, lexical=False)


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
    chunk_id = result.chunk_id
    if not chunk_id:
        raw_chunk_index = result.metadata.get("chunk_index")
        chunk_id = str(raw_chunk_index) if raw_chunk_index is not None else None
    if not chunk_id:
        chunk_id = hashlib.sha256(result.content.encode("utf-8")).hexdigest()[:16]
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
