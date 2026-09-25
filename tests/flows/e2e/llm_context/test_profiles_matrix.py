"""E2E matrix for built-in LLM context profiles."""
from __future__ import annotations

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.models import FlowConfig
from tests.flows.e2e.llm_context.harness import (
    call_text,
    cleanup_flow_context,
    context_config,
    index_rag_document,
    run_context_flow,
    single_node_flow,
    stale_messages,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("profile", "expect_rag"),
    [("off", False), ("compact", False), ("standard", True)],
)
async def test_context_profile_controls_retrieval_and_window(
    app,
    rag_app,
    di: FlowsDi,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
    profile: str,
    expect_rag: bool,
) -> None:
    """off/compact не retrieval, standard добавляет RAG и режет закрытую историю."""
    _ = app, rag_app
    flow_id = f"ctx-profile-{profile}-{unique_id}"
    namespace = f"ctx-profile-{profile}-{unique_id}"
    collection_id = f"collection-{profile}-{unique_id}"
    rag_marker = f"RAG_PROFILE_{profile}_{unique_id}"
    context_id = f"context-{profile}-{unique_id}"
    await FlowConfig.create_version(
        single_node_flow(
            flow_id=flow_id,
            prompt=f"PROFILE_{profile}_{unique_id}",
            llm_context=context_config(
                profile=profile,
                active_window_tokens=20,
            ),
            rag_namespace=namespace,
            collection_id=collection_id,
        )
    )
    try:
        await index_rag_document(
            di=di,
            namespace=namespace,
            collection_id=collection_id,
            marker=rag_marker,
        )
        query = f"QUERY_PROFILE_{profile}_{unique_id}"
        call, _ = await run_context_flow(
            di=di,
            flow_id=flow_id,
            query=query,
            response=f"RESPONSE_PROFILE_{profile}",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=context_id,
            initial_messages=stale_messages(
                context_id=context_id,
                task_id=f"task-{context_id}",
                marker=f"OLD_CONTEXT_{profile}_{unique_id}",
            ),
        )
        prompt = call_text(call)
        assert query in prompt
        assert (rag_marker in prompt) is expect_rag
        if profile != "off":
            assert f"OLD_CONTEXT_{profile}_{unique_id}" not in prompt
    finally:
        await cleanup_flow_context(
            di=di,
            flow_id=flow_id,
            namespaces=[namespace],
            auth_headers_system=auth_headers_system,
        )
