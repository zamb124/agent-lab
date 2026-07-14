"""E2E: RAG retrieval filters via min_score."""
from __future__ import annotations

import pytest

from apps.flows.src.container import FlowContainer
from tests.flows.e2e.llm_context.harness import (
    call_text,
    cleanup_flow_context,
    context_config,
    index_rag_document,
    run_context_flow,
    single_node_flow,
)

pytestmark = pytest.mark.asyncio


async def test_high_min_score_drops_weak_rag_hits(
    app,
    rag_app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
) -> None:
    """min_score=0.99 отбрасывает слабые RAG hits из prompt."""
    _ = app, rag_app
    flow_id = f"ctx-minscore-rag-{unique_id}"
    namespace = f"ctx-minscore-rag-{unique_id}"
    collection_id = f"collection-minscore-{unique_id}"
    foreign_marker = f"FOREIGN_RAG_{unique_id}"
    llm_context = context_config(profile="standard", active_window_tokens=40)
    llm_context["retrieval"] = {
        "mode": "hybrid",
        "top_k": 4,
        "rerank": False,
        "min_score": 0.99,
    }
    await container.flow_repository.set(
        single_node_flow(
            flow_id=flow_id,
            prompt="Answer from knowledge if present.",
            llm_context=llm_context,
            rag_namespace=namespace,
            collection_id=collection_id,
        )
    )
    try:
        await index_rag_document(
            container=container,
            namespace=namespace,
            collection_id=collection_id,
            marker=foreign_marker,
        )
        call, _ = await run_context_flow(
            container=container,
            flow_id=flow_id,
            query=f"QUERY_MINSCORE_RAG_ZZZZ_{unique_id}_unrelated_xyz",
            response="no knowledge",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=f"context-minscore-rag-{unique_id}",
        )
        prompt = call_text(call)
        assert foreign_marker not in prompt
    finally:
        await cleanup_flow_context(
            container=container,
            flow_id=flow_id,
            namespaces=[namespace],
            auth_headers_system=auth_headers_system,
        )
