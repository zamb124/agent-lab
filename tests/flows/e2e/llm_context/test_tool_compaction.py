"""E2E: tool-result compaction through llm_node + MockLLM capture."""
from __future__ import annotations

import pytest

from apps.flows.src.container import FlowContainer
from apps.flows.src.runtime.a2a_messages import (
    build_assistant_message,
    build_tool_result_message,
    build_user_message,
)
from core.clients.llm import LLMToolCall
from tests.flows.e2e.llm_context.harness import (
    call_text,
    cleanup_flow_context,
    context_config,
    run_context_flow,
    single_node_flow,
)

pytestmark = pytest.mark.asyncio


async def test_context_layer_compacts_huge_tool_result_in_prompt(
    app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
) -> None:
    """Огромный tool result в state.messages сжимается до digest перед LLM call."""
    _ = app
    flow_id = f"ctx-tool-compact-{unique_id}"
    context_id = f"context-tool-compact-{unique_id}"
    task_id = f"task-{context_id}"
    huge_payload = "HUGE_TOOL_PAYLOAD_" + ("result-chunk " * 400)
    await container.flow_repository.set(
        single_node_flow(
            flow_id=flow_id,
            prompt="Answer after the tool result.",
            llm_context=context_config(
                mode="smart",
                retrieval_mode="off",
                memory="off",
                max_input_tokens=2_048,
                active_window_tokens=2_000,
                tool_result_tokens=32,
            ),
        )
    )
    try:
        call, _ = await run_context_flow(
            container=container,
            flow_id=flow_id,
            query=f"QUERY_TOOL_COMPACT_{unique_id}",
            response="compacted ok",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=context_id,
            initial_messages=[
                build_user_message(
                    f"ASK_TOOL_{unique_id}",
                    "agent",
                    context_id=context_id,
                    task_id=task_id,
                ),
                build_assistant_message(
                    "",
                    "agent",
                    tool_calls=[
                        LLMToolCall(
                            id="call-huge-1",
                            name="lookup",
                            arguments={"q": "billing"},
                        )
                    ],
                    context_id=context_id,
                    task_id=task_id,
                ),
                build_tool_result_message(
                    "call-huge-1",
                    huge_payload,
                    "agent",
                    context_id=context_id,
                    task_id=task_id,
                ),
            ],
        )
        prompt = call_text(call)
        assert "tool result compacted" in prompt
        assert "HUGE_TOOL_PAYLOAD_" not in prompt
        assert f"QUERY_TOOL_COMPACT_{unique_id}" in prompt
    finally:
        await cleanup_flow_context(
            container=container,
            flow_id=flow_id,
            namespaces=[],
            auth_headers_system=auth_headers_system,
        )
