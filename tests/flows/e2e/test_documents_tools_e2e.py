"""E2E coverage for flow document tools over real flows, Office BFF and files storage."""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from io import BytesIO
from typing import Any, cast

import pytest
from docx import Document
from openpyxl import Workbook, load_workbook

from tests.flows._a2a_v1 import GET_TASK, SEND_MESSAGE, a2a_rpc

pytestmark = [
    pytest.mark.real_taskiq,
    pytest.mark.timeout(180, func_only=True),
    pytest.mark.usefixtures("frontend_service"),
]
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _headers(auth_headers_system: dict[str, str]) -> dict[str, str]:
    return {**auth_headers_system, "X-Platform-Namespace": "default"}


def _docx_bytes(*paragraphs: str) -> bytes:
    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _docx_text(data: bytes) -> str:
    doc = Document(BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend((cell.text for cell in row.cells))
    return "\n".join(parts)


def _xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("Workbook.active is required")
    ws.title = "Sheet1"
    ws["A1"] = "OLD_CELL"
    ws["B2"] = "keep"
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


async def _create_flow(flows_client_http, headers: dict[str, str], flow_id: str) -> None:
    response = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": f"Documents tools {flow_id}",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Use the provided document tools to edit the attached file.",
                    "tools": [
                        "documents_open_file",
                        "documents_replace_text",
                        "documents_append_text",
                        "documents_update_cells",
                    ],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text


_A2A_OPEN_STATES = frozenset({"TASK_STATE_SUBMITTED", "TASK_STATE_WORKING"})
_A2A_GET_TASK_POLL_SECONDS = 60.0
_A2A_GET_TASK_POLL_INTERVAL_SECONDS = 0.3


def _a2a_task(data: dict[str, Any]) -> dict[str, Any]:
    assert "error" not in data, data.get("error")
    task = data.get("result")
    assert isinstance(task, dict), data
    return task


def _a2a_task_state(task: dict[str, Any]) -> str:
    status = task.get("status")
    assert isinstance(status, dict), task
    state = status.get("state")
    assert isinstance(state, str) and state, task
    return state


async def _send_file_message(
    flows_client_http,
    headers: dict[str, str],
    *,
    flow_id: str,
    context_id: str,
    file_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> dict[str, Any]:
    """Enqueue SendMessage without holding a flows granian worker for the graph."""
    response = await flows_client_http.post(
        f"/flows/api/v1/{flow_id}",
        headers=headers,
        json=a2a_rpc(
            SEND_MESSAGE,
            {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "contextId": context_id,
                    "parts": [
                        {"text": "Edit the attached document."},
                        {
                            "raw": base64.b64encode(file_bytes).decode("ascii"),
                            "filename": file_name,
                            "mediaType": mime_type,
                        },
                    ],
                },
                "configuration": {"returnImmediately": True},
            },
        ),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    task = _a2a_task(data)
    if _a2a_task_state(task) not in _A2A_OPEN_STATES:
        assert _a2a_task_state(task) == "TASK_STATE_COMPLETED", data
        return data
    task_id = task.get("id")
    assert isinstance(task_id, str) and task_id, data
    deadline = time.monotonic() + _A2A_GET_TASK_POLL_SECONDS
    last = data
    while time.monotonic() < deadline:
        poll = await flows_client_http.post(
            f"/flows/api/v1/{flow_id}",
            headers=headers,
            json=a2a_rpc(GET_TASK, {"id": task_id}),
        )
        assert poll.status_code == 200, poll.text
        last = poll.json()
        polled = _a2a_task(last)
        if _a2a_task_state(polled) not in _A2A_OPEN_STATES:
            assert _a2a_task_state(polled) == "TASK_STATE_COMPLETED", last
            return last
        await asyncio.sleep(_A2A_GET_TASK_POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"A2A task {task_id} did not complete within {_A2A_GET_TASK_POLL_SECONDS}s: {last}"
    )


def _file_item_dict(item: object) -> dict[str, Any] | None:
    if isinstance(item, dict):
        return cast(dict[str, Any], item)
    dump = getattr(item, "model_dump", None)
    if callable(dump):
        dumped = dump(mode="json", exclude_none=True)
        if isinstance(dumped, dict):
            return cast(dict[str, Any], dumped)
    return None


def _file_document(item: dict[str, Any]) -> dict[str, Any] | None:
    capabilities = item.get("capabilities")
    document = item.get("document")
    if isinstance(document, dict):
        return document
    if isinstance(capabilities, dict):
        cap_document = capabilities.get("document")
        if isinstance(cap_document, dict):
            return cap_document
    return None


async def _state_file(
    container, *, flow_id: str, context_id: str, file_name: str, require_document: bool = False
) -> dict[str, Any]:
    session_id = f"{flow_id}:{context_id}"
    fallback: dict[str, Any] | None = None
    for _ in range(30):
        state = await container.workflow_runtime.get_state(session_id)
        if state:
            files_raw = (
                state.get("files") if isinstance(state, dict) else getattr(state, "files", [])
            )
            files = files_raw if isinstance(files_raw, list) else []
            matches = [
                file_item
                for item in files
                if (file_item := _file_item_dict(item)) is not None
                and file_item.get("original_name") == file_name
            ]
            for item in reversed(matches):
                if _file_document(item):
                    return item
            if matches:
                fallback = matches[-1]
                if not require_document:
                    return fallback
        await asyncio.sleep(0.1)
    if fallback is not None and (not require_document):
        return fallback
    raise AssertionError(f"File {file_name!r} was not persisted in state {session_id!r}")


async def _download_flow_file(flows_client_http, headers: dict[str, str], file_id: str) -> bytes:
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
async def test_agent_edits_uploaded_docx_with_documents_tools(
    flows_client_http,
    office_service,
    mock_llm_redis,
    auth_headers_system,
    container,
    unique_id: str,
) -> None:
    _ = office_service
    headers = _headers(auth_headers_system)
    flow_id = f"documents_docx_{unique_id}"
    context_id = f"ctx-docx-{uuid.uuid4().hex}"
    file_name = f"agent-doc-{unique_id}.docx"
    await mock_llm_redis(
        [
            {
                "type": "tool_call",
                "tool": "documents_open_file",
                "args": {"file_name": file_name},
            },
            {
                "type": "tool_call",
                "tool": "documents_replace_text",
                "args": {
                    "file_name": file_name,
                    "find": "ORIGINAL_TOKEN",
                    "replace": "UPDATED_TOKEN",
                    "match_case": True,
                },
            },
            {
                "type": "tool_call",
                "tool": "documents_append_text",
                "args": {
                    "file_name": file_name,
                    "text": "APPENDED_TOKEN",
                },
            },
            {"type": "text", "content": "Document updated."},
        ]
    )
    await _create_flow(flows_client_http, headers, flow_id)
    try:
        await _send_file_message(
            flows_client_http,
            headers,
            flow_id=flow_id,
            context_id=context_id,
            file_name=file_name,
            mime_type=DOCX_MIME,
            file_bytes=_docx_bytes("Before ORIGINAL_TOKEN", "Second paragraph"),
        )
        file_item = await _state_file(
            container,
            flow_id=flow_id,
            context_id=context_id,
            file_name=file_name,
            require_document=True,
        )
        document = _file_document(file_item)
        assert document
        assert document["file_id"] == file_item["file_id"]
        assert isinstance(document["catalog_id"], str) and document["catalog_id"]
        assert document["editor_url"].startswith("/documents/embed/edit/")
        stored = await _download_flow_file(flows_client_http, headers, file_item["file_id"])
        text = _docx_text(stored)
        assert "UPDATED_TOKEN" in text
        assert "APPENDED_TOKEN" in text
        assert "ORIGINAL_TOKEN" not in text
    finally:
        await flows_client_http.delete(f"/flows/api/v1/flows/{flow_id}", headers=headers)


@pytest.mark.asyncio
async def test_agent_updates_uploaded_xlsx_with_documents_tool(
    flows_client_http,
    office_service,
    mock_llm_redis,
    auth_headers_system,
    container,
    unique_id: str,
) -> None:
    _ = office_service
    headers = _headers(auth_headers_system)
    flow_id = f"documents_xlsx_{unique_id}"
    context_id = f"ctx-xlsx-{uuid.uuid4().hex}"
    file_name = f"agent-sheet-{unique_id}.xlsx"
    await mock_llm_redis(
        [
            {
                "type": "tool_call",
                "tool": "documents_open_file",
                "args": {"file_name": file_name},
            },
            {
                "type": "tool_call",
                "tool": "documents_update_cells",
                "args": {
                    "file_name": file_name,
                    "sheet": "Sheet1",
                    "cells": {"A1": "UPDATED_CELL", "B2": 42},
                },
            },
            {"type": "text", "content": "Spreadsheet updated."},
        ]
    )
    await _create_flow(flows_client_http, headers, flow_id)
    try:
        await _send_file_message(
            flows_client_http,
            headers,
            flow_id=flow_id,
            context_id=context_id,
            file_name=file_name,
            mime_type=XLSX_MIME,
            file_bytes=_xlsx_bytes(),
        )
        file_item = await _state_file(
            container,
            flow_id=flow_id,
            context_id=context_id,
            file_name=file_name,
            require_document=True,
        )
        document = _file_document(file_item)
        assert document
        assert document["file_id"] == file_item["file_id"]
        assert isinstance(document["catalog_id"], str) and document["catalog_id"]
        assert document["editor_url"].startswith("/documents/embed/edit/")
        stored = await _download_flow_file(flows_client_http, headers, file_item["file_id"])
        wb = load_workbook(BytesIO(stored))
        ws = wb["Sheet1"]
        assert ws["A1"].value == "UPDATED_CELL"
        assert ws["B2"].value == 42
    finally:
        await flows_client_http.delete(f"/flows/api/v1/flows/{flow_id}", headers=headers)
