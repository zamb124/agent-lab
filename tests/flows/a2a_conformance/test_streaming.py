"""SendStreamingMessage SSE StreamResponse shape."""

from __future__ import annotations

import pytest

from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow
from tests.flows.a2a_conformance.helpers.rpc import send_streaming, stream_terminal_state

pytestmark = [pytest.mark.asyncio, pytest.mark.real_taskiq, pytest.mark.timeout(90, func_only=True)]


async def test_send_streaming_message_frames_are_stream_response(
    client, unique_id: str
) -> None:
    flow_id = f"a2a_conf_stream_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        frames = await send_streaming(
            client,
            flow_id,
            f"stream-{unique_id}",
            context_id=f"ctx-stream-{unique_id}",
        )
        assert frames
        for frame in frames:
            if "error" in frame:
                continue
            result = frame["result"]
            assert "kind" not in result
            assert any(
                key in result for key in ("task", "message", "statusUpdate", "artifactUpdate")
            )
        assert stream_terminal_state(frames) == "TASK_STATE_COMPLETED"
    finally:
        await delete_flow(client, flow_id)
