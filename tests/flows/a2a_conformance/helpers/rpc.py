"""HTTP JSON-RPC + SSE helpers for A2A conformance tests."""

from __future__ import annotations

import json
import uuid
from typing import Any

from core.a2a.methods import SEND_MESSAGE, SEND_STREAMING_MESSAGE
from core.types import JsonObject, require_json_object
from tests.flows._a2a_v1 import A2A_HEADERS, a2a_headers, a2a_rpc, a2a_text_message
from tests.flows.a2a_conformance.helpers.schema import (
    assert_valid_stream_result,
    assert_valid_task,
)


def rpc_url(flow_id: str) -> str:
    return f"/flows/api/v1/{flow_id}"


async def post_rpc(
    client: Any,
    flow_id: str,
    method: str,
    params: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    rpc_id: str | int | None = None,
) -> JsonObject:
    response = await client.post(
        rpc_url(flow_id),
        headers=a2a_headers(headers or A2A_HEADERS),
        json=a2a_rpc(method, params, rpc_id=rpc_id),
    )
    assert response.status_code == 200, response.text
    return require_json_object(response.json(), "jsonrpc.response")


async def send_message(
    client: Any,
    flow_id: str,
    text: str,
    *,
    context_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    configuration: dict[str, Any] | None = None,
) -> JsonObject:
    params: dict[str, Any] = {"message": a2a_text_message(text, context_id=context_id)}
    if metadata is not None:
        params["metadata"] = metadata
    if configuration is not None:
        params["configuration"] = configuration
    envelope = await post_rpc(client, flow_id, SEND_MESSAGE, params)
    assert "error" not in envelope, envelope
    result = require_json_object(envelope["result"], "SendMessage.result")
    _ = assert_valid_task(result)
    return result


async def send_streaming(
    client: Any,
    flow_id: str,
    text: str,
    *,
    context_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[JsonObject]:
    params: dict[str, Any] = {"message": a2a_text_message(text, context_id=context_id)}
    if metadata is not None:
        params["metadata"] = metadata
    response = await client.post(
        rpc_url(flow_id),
        headers=a2a_headers({**A2A_HEADERS, "Accept": "text/event-stream"}),
        json=a2a_rpc(SEND_STREAMING_MESSAGE, params, rpc_id=str(uuid.uuid4())),
        timeout=60,
    )
    assert response.status_code == 200, response.text
    assert "text/event-stream" in response.headers.get("content-type", "")
    return parse_sse_results(response.text)


def parse_sse_results(body: str) -> list[JsonObject]:
    frames: list[JsonObject] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            continue
        envelope = require_json_object(json.loads(payload), "sse.envelope")
        assert envelope.get("jsonrpc") == "2.0"
        if "error" in envelope:
            frames.append(envelope)
            continue
        result = require_json_object(envelope["result"], "sse.result")
        _ = assert_valid_stream_result(result)
        frames.append(envelope)
    return frames


def stream_terminal_state(frames: list[JsonObject]) -> str | None:
    for frame in reversed(frames):
        result = frame.get("result")
        if not isinstance(result, dict):
            continue
        status_update = result.get("statusUpdate")
        if isinstance(status_update, dict):
            status = status_update.get("status")
            if isinstance(status, dict) and isinstance(status.get("state"), str):
                state = status["state"]
                if state.startswith("TASK_STATE_") and state not in {
                    "TASK_STATE_WORKING",
                    "TASK_STATE_SUBMITTED",
                    "TASK_STATE_UNSPECIFIED",
                }:
                    return state
        task = result.get("task")
        if isinstance(task, dict):
            status = task.get("status")
            if isinstance(status, dict) and isinstance(status.get("state"), str):
                return status["state"]
    return None
