"""E2E: agent create_viz via A2A + MockLLM, then Office editor-config / stream / export."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, cast

import pytest

from core.viz.models import VIZ_CONTENT_TYPE, parse_viz_document_bytes
from tests.office.access_helpers import parse_viz_stream_url

pytestmark = [
    pytest.mark.real_taskiq,
    pytest.mark.timeout(180, func_only=True),
    pytest.mark.usefixtures("frontend_service"),
]


def _headers(auth_headers_system: dict[str, str]) -> dict[str, str]:
    return {**auth_headers_system, "X-Platform-Namespace": "default"}


async def _create_flow(flows_client_http, headers: dict[str, str], flow_id: str) -> None:
    response = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": f"Viz tools {flow_id}",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Use viz tools to create and export visualizations.",
                    "tools": ["create_viz", "viz_open_file", "export_viz"],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text


async def _send_text(
    flows_client_http,
    headers: dict[str, str],
    *,
    flow_id: str,
    context_id: str,
    text: str,
) -> dict[str, Any]:
    response = await flows_client_http.post(
        f"/flows/api/v1/{flow_id}",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": f"test-{uuid.uuid4().hex}",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "user",
                    "contextId": context_id,
                    "parts": [{"kind": "text", "text": text}],
                }
            },
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    task = data.get("result", {})
    assert task.get("status", {}).get("state") == "completed", data
    return data


def _file_item_dict(item: object) -> dict[str, Any] | None:
    if isinstance(item, dict):
        return cast(dict[str, Any], item)
    dump = getattr(item, "model_dump", None)
    if callable(dump):
        dumped = dump(mode="json", exclude_none=True)
        if isinstance(dumped, dict):
            return cast(dict[str, Any], dumped)
    return None


async def _wait_state_viz_file(
    container,
    *,
    flow_id: str,
    context_id: str,
) -> dict[str, Any]:
    session_id = f"{flow_id}:{context_id}"
    for _ in range(50):
        state = await container.workflow_runtime.get_state(session_id)
        if state:
            files_raw = (
                state.get("files") if isinstance(state, dict) else getattr(state, "files", [])
            )
            files = files_raw if isinstance(files_raw, list) else []
            for item in reversed(files):
                file_item = _file_item_dict(item)
                if file_item is None:
                    continue
                name = file_item.get("original_name")
                content_type = file_item.get("content_type")
                if (
                    isinstance(name, str)
                    and name.endswith(".viz")
                    and content_type == VIZ_CONTENT_TYPE
                ):
                    return file_item
                if isinstance(name, str) and name.endswith(".viz"):
                    return file_item
        await asyncio.sleep(0.1)
    raise AssertionError(f"No .viz file in state {session_id!r}")


def _tool_results(state: object) -> dict[str, Any]:
    raw = state.get("tool_results") if isinstance(state, dict) else getattr(state, "tool_results", {})
    if not isinstance(raw, dict):
        return {}
    return cast(dict[str, Any], raw)


def _json_object_from_tool_result(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return cast(dict[str, Any], raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


async def _download_file(flows_client_http, headers: dict[str, str], file_id: str) -> bytes:
    deadline = time.monotonic() + 30.0
    last_status = 0
    last_body = ""
    while time.monotonic() < deadline:
        response = await flows_client_http.get(
            f"/frontend/api/v1/files/download/{file_id}", headers=headers
        )
        if response.status_code == 200:
            return response.content
        last_status = response.status_code
        last_body = response.text
        if response.status_code != 404:
            break
        await asyncio.sleep(0.2)
    raise AssertionError(
        f"download {file_id!r} failed: status={last_status}, body={last_body}"
    )


@pytest.mark.asyncio
async def test_agent_create_viz_office_roundtrip_and_export(
    flows_client_http,
    office_client_http,
    office_service,
    mock_llm_redis,
    auth_headers_system,
    container,
    unique_id: str,
) -> None:
    _ = office_service
    headers = _headers(auth_headers_system)
    flow_id = f"viz_tools_{unique_id}"
    context_id = f"ctx-viz-{uuid.uuid4().hex}"
    title = f"AgentFunnel {unique_id}"
    source = "flowchart TD\n  Lead-->Qualify-->Win"
    await mock_llm_redis(
        [
            {
                "type": "tool_call",
                "tool": "create_viz",
                "args": {
                    "kind": "flowchart",
                    "title": title,
                    "source": source,
                },
            },
            {"type": "text", "content": "Visualization created."},
        ]
    )
    await _create_flow(flows_client_http, headers, flow_id)
    try:
        await _send_text(
            flows_client_http,
            headers,
            flow_id=flow_id,
            context_id=context_id,
            text="Create a funnel flowchart visualization.",
        )
        file_item = await _wait_state_viz_file(
            container, flow_id=flow_id, context_id=context_id
        )
        file_id = file_item["file_id"]
        assert isinstance(file_id, str) and file_id

        session_id = f"{flow_id}:{context_id}"
        state = await container.workflow_runtime.get_state(session_id)
        assert state is not None
        create_result = None
        for value in _tool_results(state).values():
            parsed = _json_object_from_tool_result(value)
            if (
                parsed is not None
                and parsed.get("success") is True
                and isinstance(parsed.get("blocks"), list)
                and parsed["blocks"]
                and isinstance(parsed["blocks"][0], dict)
                and parsed["blocks"][0].get("type") == "viz"
            ):
                create_result = parsed
                break
        assert create_result is not None, f"create_viz blocks missing: {_tool_results(state)}"
        assert create_result["blocks"][0]["type"] == "viz"
        assert create_result["blocks"][0]["file_id"] == file_id

        editor = await office_client_http.get(
            f"/documents/api/v1/files/{file_id}/editor-config",
            headers=headers,
        )
        assert editor.status_code == 200, editor.text
        editor_body = editor.json()
        assert editor_body["handler"] == "viz"
        assert editor_body["viz"]["title"] == title
        stream_url = parse_viz_stream_url(editor_body)
        stream = await office_client_http.get(stream_url)
        assert stream.status_code == 200, stream.text
        document = parse_viz_document_bytes(stream.content)
        assert document.title == title
        assert document.spec.get("source") == source

        await mock_llm_redis(
            [
                {
                    "type": "tool_call",
                    "tool": "export_viz",
                    "args": {"file_id": file_id, "format": "svg"},
                },
                {"type": "text", "content": "Exported SVG."},
            ]
        )
        await _send_text(
            flows_client_http,
            headers,
            flow_id=flow_id,
            context_id=context_id,
            text="Export the visualization to SVG.",
        )
        session_id = f"{flow_id}:{context_id}"
        svg_file_id: str | None = None
        for _ in range(50):
            state = await container.workflow_runtime.get_state(session_id)
            assert state is not None
            files_raw = (
                state.get("files") if isinstance(state, dict) else getattr(state, "files", [])
            )
            files = files_raw if isinstance(files_raw, list) else []
            for item in reversed(files):
                file_obj = _file_item_dict(item)
                if file_obj is None:
                    continue
                name = file_obj.get("original_name")
                if isinstance(name, str) and name.endswith(".svg"):
                    candidate = file_obj.get("file_id")
                    if isinstance(candidate, str) and candidate:
                        svg_file_id = candidate
                        break
            if svg_file_id:
                break
            await asyncio.sleep(0.1)
        assert svg_file_id is not None, "export_viz SVG sidecar missing from state.files"
        svg_bytes = await _download_file(flows_client_http, headers, svg_file_id)
        assert title in svg_bytes.decode("utf-8")
        assert b"<svg" in svg_bytes
    finally:
        await flows_client_http.delete(f"/flows/api/v1/flows/{flow_id}", headers=headers)


@pytest.mark.asyncio
async def test_agent_create_viz_rejects_invalid_args(
    flows_client_http,
    mock_llm_redis,
    auth_headers_system,
    container,
    unique_id: str,
) -> None:
    headers = _headers(auth_headers_system)
    flow_id = f"viz_tools_neg_{unique_id}"
    context_id = f"ctx-viz-neg-{uuid.uuid4().hex}"
    await mock_llm_redis(
        [
            {
                "type": "tool_call",
                "tool": "create_viz",
                "args": {"kind": "flowchart", "title": f"Bad {unique_id}", "source": ""},
            },
            {"type": "text", "content": "Could not create visualization."},
        ]
    )
    await _create_flow(flows_client_http, headers, flow_id)
    try:
        await _send_text(
            flows_client_http,
            headers,
            flow_id=flow_id,
            context_id=context_id,
            text="Create a flowchart without source.",
        )
        session_id = f"{flow_id}:{context_id}"
        state = await container.workflow_runtime.get_state(session_id)
        assert state is not None
        files_raw = state.get("files") if isinstance(state, dict) else getattr(state, "files", [])
        files = files_raw if isinstance(files_raw, list) else []
        for item in files:
            file_obj = _file_item_dict(item)
            if file_obj is None:
                continue
            name = file_obj.get("original_name")
            assert not (isinstance(name, str) and name.endswith(".viz"))

        failed = None
        for value in _tool_results(state).values():
            parsed = _json_object_from_tool_result(value)
            if parsed is not None and parsed.get("success") is False:
                failed = parsed
                break
        assert failed is not None
        assert "error" in failed
    finally:
        await flows_client_http.delete(f"/flows/api/v1/flows/{flow_id}", headers=headers)
