"""E2E проверка стандартных режимов A2A для flows API.

Инфраструктура настоящая: FastAPI A2A API, TaskIQ worker, PostgreSQL, Redis и
code runner. Моков и monkeypatch здесь нет; flow детерминированный и не вызывает LLM.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from tests.flows._a2a_v1 import A2A_HEADERS, a2a_headers

pytestmark = [pytest.mark.e2e, pytest.mark.real_taskiq, pytest.mark.timeout(90, func_only=True)]


def _message(text: str, context_id: str) -> dict[str, Any]:
    return {
        "messageId": str(uuid.uuid4()),
        "role": "ROLE_USER",
        "parts": [{"text": text}],
        "contextId": context_id,
    }


def _metadata(unique_id: str) -> dict[str, Any]:
    return {
        "branch": "default",
        "variables": {
            "salutation": "hello-from-request-var",
            "branch_id": f"runtime-branch-{unique_id}",
            "extra": f"client-var-{unique_id}",
        },
    }


def _rpc_body(
    method: str,
    unique_id: str,
    *,
    context_id: str,
    return_immediately: bool = False,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "message": _message(f"run {method}", context_id),
        "metadata": _metadata(unique_id),
    }
    if return_immediately:
        params["configuration"] = {"returnImmediately": True}
    return {
        "jsonrpc": "2.0",
        "id": f"{method}-{unique_id}-{uuid.uuid4().hex}",
        "method": method,
        "params": params,
    }


def _parse_sse(text: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            continue
        frame = json.loads(payload)
        assert isinstance(frame, dict)
        frames.append(frame)
    return frames


def _parts_text(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
        data = part.get("data")
        if isinstance(data, dict):
            res = data.get("res")
            if isinstance(res, str):
                chunks.append(res)
            result_preview = data.get("result_preview")
            if isinstance(result_preview, str):
                chunks.append(result_preview)
    return "".join(chunks)


def _task_text(task: dict[str, Any]) -> str:
    chunks: list[str] = []
    status = task.get("status")
    if isinstance(status, dict):
        message = status.get("message")
        if isinstance(message, dict):
            chunks.append(_parts_text(message.get("parts")))
    artifacts = task.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                chunks.append(_parts_text(artifact.get("parts")))
    return "".join(chunks)


def _stream_text(frames: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for frame in frames:
        assert "error" not in frame, frame.get("error")
        result = frame.get("result")
        if not isinstance(result, dict):
            continue
        if "artifactUpdate" in result:
            body = result.get("artifactUpdate")
            if isinstance(body, dict):
                artifact = body.get("artifact")
                if isinstance(artifact, dict):
                    chunks.append(_parts_text(artifact.get("parts")))
        elif "statusUpdate" in result:
            body = result.get("statusUpdate")
            if isinstance(body, dict):
                status = body.get("status")
                if isinstance(status, dict):
                    message = status.get("message")
                    if isinstance(message, dict):
                        chunks.append(_parts_text(message.get("parts")))
        elif "message" in result:
            message = result.get("message")
            if isinstance(message, dict):
                chunks.append(_parts_text(message.get("parts")))
    return "".join(chunks)


def _stream_terminal_state(frames: list[dict[str, Any]]) -> str:
    state = ""
    for frame in frames:
        result = frame.get("result")
        if not isinstance(result, dict):
            continue
        body = result.get("statusUpdate")
        if not isinstance(body, dict):
            continue
        status = body.get("status")
        if isinstance(status, dict) and isinstance(status.get("state"), str):
            state = status["state"]
    return state


def _task_from_json_rpc(data: dict[str, Any]) -> dict[str, Any]:
    assert "error" not in data, data.get("error")
    task = data.get("result")
    assert isinstance(task, dict)
    return task


async def _create_modes_flow(client: Any, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=A2A_HEADERS,
        json={
            "flow_id": flow_id,
            "name": "A2A Modes E2E",
            "entry": "compose",
            "nodes": {
                "compose": {
                    "type": "code",
                    "code": (
                        "async def run(args, state):\n"
                        "    state['response'] = "
                        "f\"A2A_OK:{args['salutation']}|"
                        "{args['target_branch_id']}|{args['extra']}\"\n"
                        "    return state\n"
                    ),
                    "input_mapping": {
                        "salutation": "@var:salutation",
                        "target_branch_id": "@var:target_branch_id",
                        "extra": "@var:extra",
                    },
                },
            },
            "edges": [{"from_node": "compose", "to_node": None}],
            "variables": {
                "salutation": "fallback-salutation",
                "target_branch_id": "fallback-target",
                "extra": "fallback-extra",
            },
        },
    )
    assert response.status_code == 200, response.text

async def _poll_task(client: Any, flow_id: str, task_id: str) -> dict[str, Any]:
    for _ in range(40):
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": f"get-{uuid.uuid4().hex}",
                "method": "GetTask",
                "params": {"id": task_id, "historyLength": 20},
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, dict)
        task = data.get("result")
        if isinstance(task, dict):
            status = task.get("status")
            if isinstance(status, dict) and status.get("state") in {
                "TASK_STATE_COMPLETED",
                "TASK_STATE_FAILED",
                "TASK_STATE_INPUT_REQUIRED",
            }:
                return task
        await asyncio.sleep(0.25)
    raise AssertionError(f"Task {task_id} did not reach terminal state")


@pytest.mark.asyncio
async def test_a2a_standard_stream_sync_and_async_modes(client: Any, unique_id: str) -> None:
    flow_id = f"e2e_a2a_modes_{unique_id}"
    expected = f"A2A_OK:hello-from-request-var|runtime-branch-{unique_id}|client-var-{unique_id}"
    await _create_modes_flow(client, flow_id)
    try:
        stream_context_id = f"ctx-stream-{unique_id}"
        stream_response = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=a2a_headers({"Accept": "text/event-stream"}),
            json=_rpc_body(
                "SendStreamingMessage",
                unique_id,
                context_id=stream_context_id,
            ),
            timeout=45,
        )
        assert stream_response.status_code == 200, stream_response.text
        assert "text/event-stream" in stream_response.headers.get("content-type", "")
        frames = _parse_sse(stream_response.text)
        assert frames
        assert _stream_terminal_state(frames) == "TASK_STATE_COMPLETED", stream_response.text
        assert expected in _stream_text(frames)

        sync_context_id = f"ctx-sync-{unique_id}"
        sync_response = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=a2a_headers({"Accept": "application/json"}),
            json=_rpc_body(
                "SendMessage",
                unique_id,
                context_id=sync_context_id,
            ),
            timeout=45,
        )
        assert sync_response.status_code == 200, sync_response.text
        sync_data = sync_response.json()
        assert isinstance(sync_data, dict)
        sync_task = _task_from_json_rpc(sync_data)
        assert sync_task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert sync_task["contextId"] == sync_context_id
        assert expected in _task_text(sync_task)

        async_context_id = f"ctx-async-{unique_id}"
        async_response = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=a2a_headers({"Accept": "application/json"}),
            json=_rpc_body(
                "SendMessage",
                unique_id,
                context_id=async_context_id,
                return_immediately=True,
            ),
            timeout=15,
        )
        assert async_response.status_code == 200, async_response.text
        async_data = async_response.json()
        assert isinstance(async_data, dict)
        submitted_task = _task_from_json_rpc(async_data)
        assert submitted_task["status"]["state"] == "TASK_STATE_SUBMITTED"
        assert submitted_task["contextId"] == async_context_id
        task_id = submitted_task["id"]
        assert isinstance(task_id, str)
        assert task_id

        final_task = await _poll_task(client, flow_id, task_id)
        assert final_task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert final_task["contextId"] == async_context_id
        assert expected in _task_text(final_task)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
