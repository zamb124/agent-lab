"""E2E: llm_context trace metadata reaches MockLLM capture without content."""
from __future__ import annotations

import pytest

from apps.flows.src.container import FlowContainer
from tests.flows.e2e.llm_context.harness import (
    cleanup_flow_context,
    context_config,
    run_context_flow,
    single_node_flow,
    stale_messages,
)

pytestmark = pytest.mark.asyncio


async def test_mock_capture_includes_content_free_llm_context_trace(
    app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
) -> None:
    """Capture journal stores usage/selected_blocks meta without block content."""
    _ = app
    flow_id = f"ctx-trace-{unique_id}"
    context_id = f"context-trace-{unique_id}"
    await container.flow_repository.set(
        single_node_flow(
            flow_id=flow_id,
            prompt="Trace metadata probe.",
            llm_context=context_config(
                mode="window",
                retrieval_mode="off",
                memory="off",
                active_window_tokens=20,
            ),
        )
    )
    try:
        call, _ = await run_context_flow(
            container=container,
            flow_id=flow_id,
            query=f"QUERY_TRACE_{unique_id}",
            response="trace ok",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=context_id,
            initial_messages=stale_messages(
                context_id=context_id,
                task_id=f"task-{context_id}",
                marker=f"OLD_TRACE_{unique_id}",
            ),
        )
        llm_context = call.get("llm_context")
        assert isinstance(llm_context, dict)
        usage = llm_context.get("usage")
        assert isinstance(usage, dict)
        assert usage.get("total_input_tokens", 0) > 0
        assert "selected_blocks" in llm_context
        serialized = str(llm_context)
        assert "Trace metadata probe" not in serialized
        assert f"OLD_TRACE_{unique_id}" not in serialized
    finally:
        await cleanup_flow_context(
            container=container,
            flow_id=flow_id,
            namespaces=[],
            auth_headers_system=auth_headers_system,
        )
