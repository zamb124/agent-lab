"""Memory lifecycle switches in real flow execution."""
from __future__ import annotations

import pytest

from apps.flows.src.container import FlowContainer
from core.rag.llm_context_memory_store import llm_context_memory_namespace_id
from tests.flows.e2e.llm_context.harness import (
    cleanup_flow_context,
    context_config,
    run_context_flow,
    single_node_flow,
    stale_messages,
)

pytestmark = pytest.mark.asyncio


async def test_memory_off_does_not_write_compaction_episode(
    app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
) -> None:
    """memory=off leaves the memory namespace unchanged for this flow."""
    _ = app
    flow_id = f"ctx-memory-off-{unique_id}"
    context_id = f"context-memory-off-{unique_id}"
    await container.flow_repository.set(
        single_node_flow(
            flow_id=flow_id,
            prompt="Memory is disabled.",
            llm_context=context_config(memory="off", retrieval_mode="off"),
        )
    )
    try:
        _, state = await run_context_flow(
            container=container,
            flow_id=flow_id,
            query=f"QUERY_MEMORY_OFF_{unique_id}",
            response="memory off",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=context_id,
            initial_messages=stale_messages(
                context_id=context_id,
                task_id=f"task-{context_id}",
                marker=f"OLD_MEMORY_OFF_{unique_id}",
            ),
        )
        documents = await container.rag_repository.list_with_filters(
            llm_context_memory_namespace_id("system"),
            {
                "flow_id": flow_id,
                "session_id": state.session_id,
                "source": "llm_context_compaction",
            },
            limit=10,
        )
        assert documents == []
    finally:
        await cleanup_flow_context(
            container=container,
            flow_id=flow_id,
            namespaces=[],
            auth_headers_system=auth_headers_system,
        )
