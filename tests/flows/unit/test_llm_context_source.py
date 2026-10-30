from __future__ import annotations

import pytest

from core.llm_context import (
    LLMContextBudget,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
    LLMContextSourceRequest,
)
from apps.flows.src.models.rag_resource_bind import RagResourceBindParams
from apps.flows.src.runtime.llm_context_source import RAGLLMContextSource
from core.rag import RAGSearchResult
from apps.flows.src.runtime.llm_context_source import _clamp_score
from core.rag_indexing_schema import SearchChannelsDefaults


class CapturingRagClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def search(self, namespace_id: str, query: str, **kwargs):
        self.calls.append({"namespace_id": namespace_id, "query": query, **kwargs})
        return self.response


class CapturingServiceClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def post(self, service: str, path: str, **kwargs):
        self.calls.append({"service": service, "path": path, **kwargs})
        return {"results": [], "query": kwargs["json"]["query"], "namespace_id": "kb", "provider": "pgvector"}


def _profile(
    *,
    mode: str = "hybrid",
    top_k: int = 8,
    rerank: bool = True,
    rrf_k: int | None = None,
    freshness_weight: float | None = None,
) -> LLMContextProfile:
    return LLMContextProfile(
        mode="smart",
        budget=LLMContextBudget(
            max_input_tokens=10_000,
            output_reserve_tokens=100,
            reasoning_reserve_tokens=0,
            safety_buffer_tokens=100,
            active_window_tokens=1_000,
            memory_tokens=1_000,
            rag_tokens=2_000,
            tool_result_tokens=200,
        ),
        memory="session",
        retrieval=LLMContextRetrievalPolicy(
            mode=mode,
            top_k=top_k,
            rerank=rerank,
            rrf_k=rrf_k,
            freshness_weight=freshness_weight,
        ),
        compaction="auto",
        cache="auto",
    )


@pytest.mark.asyncio
async def test_rag_context_source_collects_reranked_rag_blocks() -> None:
    rag_client = CapturingRagClient(
        {
            "results": [
                {
                    "content": "Refunds are available within 14 days.",
                    "score": 1.25,
                    "document_id": "doc-1",
                    "document_name": "policy.md",
                    "namespace": "kb",
                    "chunk_id": "chunk-3",
                    "chunk_index": 3,
                    "provenance": {"retriever": "pgvector"},
                }
            ]
        }
    )
    source = RAGLLMContextSource(
        rag_client=rag_client,
        bind=RagResourceBindParams(
            namespace="kb",
            default_top_k=5,
            company_id="company-1",
            filters={"collection_id": "support"},
        ),
    )

    blocks = await source.collect(
        LLMContextSourceRequest(
            query="refund policy",
            policy=_profile(top_k=10),
        )
    )

    assert len(blocks) == 1
    assert blocks[0].kind == "rag"
    assert blocks[0].budget_scope == "rag"
    assert blocks[0].score == 1.0
    assert blocks[0].stable_key == "rag:kb:doc-1:chunk-3"
    assert "Refunds are available" in blocks[0].content
    assert blocks[0].provenance["retriever"] == "pgvector"
    assert rag_client.calls[0]["limit"] == 10
    assert rag_client.calls[0]["channels"] == SearchChannelsDefaults(semantic=True, lexical=True)
    assert rag_client.calls[0]["rerank"] is True
    assert rag_client.calls[0]["retrieval"] is True


@pytest.mark.asyncio
async def test_rag_context_source_skips_when_retrieval_is_off_or_query_empty() -> None:
    rag_client = CapturingRagClient({"results": []})
    source = RAGLLMContextSource(
        rag_client=rag_client,
        bind=RagResourceBindParams(namespace="kb", company_id="company-1"),
    )

    assert await source.collect(LLMContextSourceRequest(query="", policy=_profile())) == []
    assert await source.collect(
        LLMContextSourceRequest(
            query="hello",
            policy=_profile(mode="off", rerank=False),
        )
    ) == []
    assert rag_client.calls == []


@pytest.mark.asyncio
async def test_rag_context_source_handles_model_results_lexical_mode_and_fallback_keys() -> None:
    rag_client = CapturingRagClient(
        {
            "results": [
                RAGSearchResult(
                    content="Chunk with metadata index.",
                    score=0.42,
                    document_id="doc-2",
                    document_name="",
                    namespace="kb",
                    chunk_id="",
                    chunk_index=7,
                    provenance={},
                ),
                {
                    "content": "Chunk without chunk id.",
                    "score": 0.7,
                    "document_id": "doc-3",
                    "document_name": "",
                    "namespace": "kb",
                    "chunk_id": "",
                    "provenance": {},
                },
            ]
        }
    )
    source = RAGLLMContextSource(
        rag_client=rag_client,
        bind=RagResourceBindParams(namespace="kb", company_id="company-1"),
        name="!!!",
    )

    blocks = await source.collect(
        LLMContextSourceRequest(query="contract", policy=_profile(mode="lexical", rerank=False))
    )

    assert source.name == "rag.source"
    assert rag_client.calls[0]["channels"] is not None
    assert rag_client.calls[0]["channels"].model_dump() == {
        "semantic": False,
        "lexical": True,
    }
    assert blocks[0].stable_key == "rag:kb:doc-2:7"
    assert blocks[0].content.startswith("[RAG context #1 namespace=kb document=doc-2")
    assert blocks[1].stable_key.startswith("rag:kb:doc-3:")


@pytest.mark.asyncio
async def test_rag_context_source_uses_semantic_only_mode() -> None:
    rag_client = CapturingRagClient({"results": []})
    source = RAGLLMContextSource(
        rag_client=rag_client,
        bind=RagResourceBindParams(namespace="kb", company_id="company-1"),
    )

    await source.collect(
        LLMContextSourceRequest(query="contract", policy=_profile(mode="semantic", rerank=False))
    )

    assert rag_client.calls[0]["channels"] is not None
    assert rag_client.calls[0]["channels"].model_dump() == {
        "semantic": True,
        "lexical": False,
    }


@pytest.mark.asyncio
async def test_rag_context_source_rejects_invalid_response_shape() -> None:
    source = RAGLLMContextSource(
        rag_client=CapturingRagClient({"results": {}}),
        bind=RagResourceBindParams(namespace="kb", company_id="company-1"),
    )

    with pytest.raises(ValueError, match="response.results"):
        await source.collect(LLMContextSourceRequest(query="hello", policy=_profile()))


def test_rag_context_source_score_guard_handles_invalid_values() -> None:
    assert _clamp_score("not-a-number") is None
    assert _clamp_score(float("nan")) is None
    assert _clamp_score(-0.5) == 0.0


@pytest.mark.asyncio
async def test_rag_context_source_passes_advanced_retrieval_options() -> None:
    rag_client = CapturingRagClient({"results": []})
    source = RAGLLMContextSource(
        rag_client=rag_client,
        bind=RagResourceBindParams(namespace="kb", company_id="company-1"),
    )

    await source.collect(
        LLMContextSourceRequest(
            query="refund policy",
            policy=_profile(rrf_k=40, freshness_weight=0.2),
        )
    )

    assert rag_client.calls[0]["channels"] == SearchChannelsDefaults(semantic=True, lexical=True)
    assert rag_client.calls[0]["rerank"] is True
    assert rag_client.calls[0]["retrieval"] is True
    assert rag_client.calls[0]["rrf_k"] == 40
    assert rag_client.calls[0]["freshness_weight"] == 0.2


@pytest.mark.asyncio
async def test_rag_llm_context_source_merges_bind_filters() -> None:
    rag_client = CapturingRagClient({"results": []})
    source = RAGLLMContextSource(
        rag_client=rag_client,
        bind=RagResourceBindParams(
            namespace="kb",
            company_id="company-1",
            filters={"collection_id": "sales", "locale": "en"},
        ),
        filters={"locale": "ru"},
    )

    await source.collect(
        LLMContextSourceRequest(query="pricing", policy=_profile()),
    )

    assert rag_client.calls[0]["filters"] == {
        "collection_id": "sales",
        "locale": "ru",
    }

