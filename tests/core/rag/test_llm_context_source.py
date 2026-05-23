from __future__ import annotations

import pytest

from core.llm_context import (
    LLMContextBudget,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
    LLMContextSourceRequest,
)
from core.rag import RAGLLMContextSource, RAGRepository, RagResourceBindParams, RAGSearchResult
from core.rag.llm_context_source import _clamp_score


class CapturingSearchRepository:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def search_namespace(self, **kwargs):
        self.calls.append(kwargs)
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
        retrieval=LLMContextRetrievalPolicy(mode=mode, top_k=top_k, rerank=rerank),
        compaction="auto",
        cache="auto",
    )


@pytest.mark.asyncio
async def test_rag_context_source_collects_reranked_rag_blocks() -> None:
    repository = CapturingSearchRepository(
        {
            "results": [
                {
                    "content": "Refunds are available within 14 days.",
                    "score": 1.25,
                    "document_id": "doc-1",
                    "document_name": "policy.md",
                    "metadata": {"chunk_index": 3},
                    "namespace": "kb",
                    "chunk_id": "chunk-3",
                    "provenance": {"retriever": "pgvector"},
                }
            ]
        }
    )
    source = RAGLLMContextSource(
        repository=repository,
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
    assert repository.calls[0]["limit"] == 10
    assert repository.calls[0]["search_options"] == {
        "channels": {"semantic": True, "lexical": True},
        "rerank": True,
        "retrieval": True,
    }


@pytest.mark.asyncio
async def test_rag_context_source_skips_when_retrieval_is_off_or_query_empty() -> None:
    repository = CapturingSearchRepository({"results": []})
    source = RAGLLMContextSource(
        repository=repository,
        bind={"namespace": "kb", "company_id": "company-1"},
    )

    assert await source.collect(LLMContextSourceRequest(query="", policy=_profile())) == []
    assert await source.collect(
        LLMContextSourceRequest(
            query="hello",
            policy=_profile(mode="off", rerank=False),
        )
    ) == []
    assert repository.calls == []


@pytest.mark.asyncio
async def test_rag_context_source_handles_model_results_lexical_mode_and_fallback_keys() -> None:
    repository = CapturingSearchRepository(
        {
            "results": [
                RAGSearchResult(
                    content="Chunk with metadata index.",
                    score=0.42,
                    document_id="doc-2",
                    document_name="",
                    metadata={"chunk_index": 7},
                    namespace="kb",
                    chunk_id=None,
                    provenance={},
                ),
                {
                    "content": "Chunk without chunk id.",
                    "score": 0.7,
                    "document_id": "doc-3",
                    "document_name": "",
                    "metadata": {},
                    "namespace": "kb",
                    "chunk_id": None,
                    "provenance": {},
                },
            ]
        }
    )
    source = RAGLLMContextSource(
        repository=repository,
        bind={"namespace": "kb", "company_id": "company-1"},
        name="!!!",
    )

    blocks = await source.collect(
        LLMContextSourceRequest(query="contract", policy=_profile(mode="lexical", rerank=False))
    )

    assert source.name == "rag.source"
    assert repository.calls[0]["search_options"]["channels"] == {
        "semantic": False,
        "lexical": True,
    }
    assert blocks[0].stable_key == "rag:kb:doc-2:7"
    assert blocks[0].content.startswith("[RAG context #1 namespace=kb document=doc-2")
    assert blocks[1].stable_key.startswith("rag:kb:doc-3:")


@pytest.mark.asyncio
async def test_rag_context_source_uses_semantic_only_mode() -> None:
    repository = CapturingSearchRepository({"results": []})
    source = RAGLLMContextSource(
        repository=repository,
        bind={"namespace": "kb", "company_id": "company-1"},
    )

    await source.collect(
        LLMContextSourceRequest(query="contract", policy=_profile(mode="semantic", rerank=False))
    )

    assert repository.calls[0]["search_options"]["channels"] == {
        "semantic": True,
        "lexical": False,
    }


@pytest.mark.asyncio
async def test_rag_context_source_rejects_invalid_response_shape() -> None:
    source = RAGLLMContextSource(
        repository=CapturingSearchRepository({"results": {}}),
        bind={"namespace": "kb", "company_id": "company-1"},
    )

    with pytest.raises(ValueError, match="response.results"):
        await source.collect(LLMContextSourceRequest(query="hello", policy=_profile()))


def test_rag_context_source_score_guard_handles_invalid_values() -> None:
    assert _clamp_score("not-a-number") is None
    assert _clamp_score(float("nan")) is None
    assert _clamp_score(-0.5) == 0.0


@pytest.mark.asyncio
async def test_rag_repository_merges_bind_filters_into_http_search_body() -> None:
    client = CapturingServiceClient()
    repository = RAGRepository(
        provider=object(),
        service_client=client,
    )

    await repository.search_namespace(
        query="pricing",
        filters={"locale": "ru"},
        bind=RagResourceBindParams(
            namespace="kb",
            company_id="company-1",
            filters={"collection_id": "sales", "locale": "en"},
        ),
    )

    assert client.calls[0]["json"]["filters"] == {
        "collection_id": "sales",
        "locale": "ru",
    }
