"""E2E: multimodal messages bypass text-first context compile."""
from __future__ import annotations

import pytest
from a2a.types import Message, Part
from a2a.types.a2a_pb2 import ROLE_USER

from apps.flows.src.container import FlowContainer
from apps.flows.src.runtime.a2a_messages import build_assistant_message, build_user_message
from core.a2a import struct_from_mapping
from tests.flows.e2e.llm_context.harness import (
    call_text,
    cleanup_flow_context,
    context_config,
    run_context_flow,
    single_node_flow,
)

pytestmark = pytest.mark.asyncio


def _multimodal_user_message(
    *,
    text: str,
    context_id: str,
    task_id: str,
) -> Message:
    png_raw = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes-for-context-bypass"
    message = Message(
        message_id=f"mm-{task_id}",
        role=ROLE_USER,
        parts=[
            Part(text=text),
            Part(
                raw=png_raw,
                filename="context-bypass.png",
                media_type="image/png",
            ),
        ],
        context_id=context_id,
        task_id=task_id,
    )
    message.metadata.CopyFrom(struct_from_mapping({"node_id": "agent"}))
    return message


async def test_multimodal_history_is_not_trimmed_by_context_layer(
    app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
) -> None:
    """Part.raw в messages отключает compile: stale text остаётся в prompt."""
    _ = app
    flow_id = f"ctx-multimodal-{unique_id}"
    context_id = f"context-multimodal-{unique_id}"
    task_id = f"task-{context_id}"
    stale_marker = f"OLD_MULTIMODAL_{unique_id}"
    await container.flow_repository.set(
        single_node_flow(
            flow_id=flow_id,
            prompt="Describe the attached image.",
            llm_context=context_config(
                mode="window",
                retrieval_mode="off",
                memory="off",
                active_window_tokens=8,
            ),
        )
    )
    try:
        call, _ = await run_context_flow(
            container=container,
            flow_id=flow_id,
            query=f"QUERY_MULTIMODAL_{unique_id}",
            response="saw image",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=context_id,
            initial_messages=[
                build_user_message(
                    f"{stale_marker} " + ("obsolete " * 80),
                    "agent",
                    context_id=context_id,
                    task_id=task_id,
                ),
                build_assistant_message(
                    f"{stale_marker}_ASSISTANT " + ("obsolete " * 80),
                    "agent",
                    context_id=context_id,
                    task_id=task_id,
                ),
                _multimodal_user_message(
                    text=f"QUERY_MULTIMODAL_{unique_id} look at this",
                    context_id=context_id,
                    task_id=task_id,
                ),
            ],
        )
        prompt = call_text(call)
        assert stale_marker in prompt
        assert any(
            isinstance(part, dict) and part.get("type") == "file"
            for message in call["messages"]
            for part in message.get("parts") or []
        )
    finally:
        await cleanup_flow_context(
            container=container,
            flow_id=flow_id,
            namespaces=[],
            auth_headers_system=auth_headers_system,
        )
