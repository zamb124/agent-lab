"""
Интеграционные тесты Google Docs — каждый тул через LlmNode + MockLLM.

ПРАВИЛО: мок только LLM. Tools, state, flow — реальные. Google API — реальный.

Auth (один из путей):
  - OAuth: google_workspace.live_test.access_token или GOOGLE_ACCESS_TOKEN
  - SA: google_service_account.json + GOOGLE_IMPERSONATE_EMAIL (Workspace DWD)

Запуск:
  GOOGLE_ACCESS_TOKEN=ya29... \\
    uv run pytest tests/flows/core/tools/test_google_docs_integration.py -m network -v -s

CI default — emulator suites: test_google_docs_emulator*.py
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from a2a.helpers.proto_helpers import get_message_text

from apps.flows.src.models import FlowConfig
from apps.flows.tools.google_docs.google_docs import (
    gdocs_append_text,
    gdocs_create_document,
    gdocs_delete_range,
    gdocs_find_replace,
    gdocs_insert_text,
    gdocs_read_document,
    gdocs_share_document,
)
from core.clients.google_docs_client import GoogleDocsClient
from core.state import ExecutionState
from core.types import JsonObject, require_json_object
from tests.fixtures.google_sheets_live import (
    google_sheets_live_auth_material,
    require_google_sheets_live_credentials,
    sheets_execution_variables,
)
from tests.flows.durable_runtime_harness import ensure_workflow_started

pytestmark = [pytest.mark.network, pytest.mark.timeout(180)]

_ALL_GDOCS_TOOLS = [
    gdocs_create_document,
    gdocs_read_document,
    gdocs_append_text,
    gdocs_insert_text,
    gdocs_find_replace,
    gdocs_delete_range,
    gdocs_share_document,
]


@pytest.fixture(autouse=True)
def _require_live_docs() -> None:
    require_google_sheets_live_credentials()


@pytest.fixture()
def gdocs_client() -> GoogleDocsClient:
    material = google_sheets_live_auth_material()
    return GoogleDocsClient(
        credentials_json=material.credentials_json,
        access_token=material.access_token,
        subject=material.subject,
    )


def _make_state(unique_id: str, flow_id: str) -> ExecutionState:
    context_id = f"ctx-gdocs-{unique_id}"
    return ExecutionState(
        task_id=f"task-gdocs-{unique_id}",
        context_id=context_id,
        user_id="u1",
        session_id=f"{flow_id}:{context_id}",
        content="Выполни",
        variables=sheets_execution_variables(),
    )


def _parse_tool_payload(content: object) -> JsonObject:
    if isinstance(content, dict):
        return require_json_object(content, "gdocs.tool_message")
    if isinstance(content, str):
        return require_json_object(json.loads(content), "gdocs.tool_message")
    raise TypeError(f"unexpected tool content type: {type(content).__name__}")


def _metadata_tool_call_id(metadata: object) -> object | None:
    """tool_call_id из dict или protobuf Struct (A2A Message.metadata)."""
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        return metadata.get("tool_call_id")
    try:
        if "tool_call_id" not in metadata:
            return None
        return metadata["tool_call_id"]
    except TypeError:
        return None


def _message_is_tool(message: object) -> bool:
    # A2A Message: и tool-result, и финальный assistant text могут иметь один role —
    # отличить можно только по metadata.tool_call_id.
    if isinstance(message, dict):
        if _metadata_tool_call_id(message.get("metadata")):
            return True
        return message.get("role") == "tool"
    return _metadata_tool_call_id(getattr(message, "metadata", None)) is not None



def _message_text(message: object) -> str:
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        return ""
    return get_message_text(message)


def _tool_payloads_from_state(state: ExecutionState) -> list[JsonObject]:
    return [
        _parse_tool_payload(_message_text(message))
        for message in state.messages
        if _message_is_tool(message)
    ]


async def _run_single_tool_flow(
    unique_id: str,
    flow_suffix: str,
    tool_ids: list[str],
    tool_call_name: str,
    tool_call_args: dict[str, Any],
    mock_llm_with_queue: Any,
    di,
) -> tuple[dict[str, Any], ExecutionState]:
    flow_id = f"gdocs_{flow_suffix}_{unique_id}"

    flow_config = FlowConfig(
        flow_id=flow_id,
        name=f"GDocs {flow_suffix}",
        entry="agent",
        nodes={
            "agent": {
                "type": "llm_node",
                "prompt": "Ты агент для Google Docs.",
                "tools": [{"tool_id": tid} for tid in tool_ids],
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
            }
        },
        edges=[],
    )
    await FlowConfig.create_version(flow_config)

    mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": tool_call_name, "args": tool_call_args},
            {"type": "text", "content": "Готово."},
        ]
    )

    flow = await di.flow_factory.get_flow(flow_id, tool_registry=di.tool_registry)
    state = _make_state(unique_id, flow_id)
    await ensure_workflow_started(
        di=di,
        state=state,
        flow_id=flow_id,
        branch_id=state.branch_id,
    )
    final_state = await flow.run(state)

    await FlowConfig.delete_by_flow_id(flow_id)
    return final_state, final_state


def test_all_gdocs_tools_are_registered_in_suite() -> None:
    names = {tool.name for tool in _ALL_GDOCS_TOOLS}
    assert names == {
        "gdocs_create_document",
        "gdocs_read_document",
        "gdocs_append_text",
        "gdocs_insert_text",
        "gdocs_find_replace",
        "gdocs_delete_range",
        "gdocs_share_document",
    }


@pytest.mark.asyncio
async def test_create_document_via_llm_node(
    app: object, unique_id: str, mock_llm_with_queue: Any, di
) -> None:
    _ = app
    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="create",
        tool_ids=["gdocs_create_document"],
        tool_call_name="gdocs_create_document",
        tool_call_args={"title": f"Agent Create {unique_id}"},
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    payload = _tool_payloads_from_state(state)[0]
    assert isinstance(payload["document_id"], str)


@pytest.mark.asyncio
async def test_read_document_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    gdocs_client: GoogleDocsClient,
    di,
) -> None:
    _ = app
    doc = await gdocs_client.create_document(f"Read Target {unique_id}")
    doc_id = str(doc["documentId"])
    await gdocs_client.append_text(doc_id, "Контент для чтения.")

    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="read",
        tool_ids=["gdocs_read_document"],
        tool_call_name="gdocs_read_document",
        tool_call_args={"document_id": doc_id},
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    assert "Контент для чтения" in str(_tool_payloads_from_state(state)[0]["text"])


@pytest.mark.asyncio
async def test_append_text_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    gdocs_client: GoogleDocsClient,
    di,
) -> None:
    _ = app
    doc = await gdocs_client.create_document(f"Append Target {unique_id}")
    doc_id = str(doc["documentId"])

    result, _state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="append",
        tool_ids=["gdocs_append_text"],
        tool_call_name="gdocs_append_text",
        tool_call_args={
            "document_id": doc_id,
            "text": "Добавленный текст из агента.\n",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    text = await gdocs_client.read_as_text(doc_id)
    assert "Добавленный текст из агента." in text


@pytest.mark.asyncio
async def test_insert_text_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    gdocs_client: GoogleDocsClient,
    di,
) -> None:
    _ = app
    doc = await gdocs_client.create_document(f"Insert Target {unique_id}")
    doc_id = str(doc["documentId"])
    await gdocs_client.append_text(doc_id, "Второй.\n")

    result, _state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="insert",
        tool_ids=["gdocs_insert_text"],
        tool_call_name="gdocs_insert_text",
        tool_call_args={
            "document_id": doc_id,
            "text": "Первый.\n",
            "index": 1,
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    text = await gdocs_client.read_as_text(doc_id)
    assert text.startswith("Первый.")
    assert "Второй." in text


@pytest.mark.asyncio
async def test_find_replace_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    gdocs_client: GoogleDocsClient,
    di,
) -> None:
    _ = app
    doc = await gdocs_client.create_document(f"FR Target {unique_id}")
    doc_id = str(doc["documentId"])
    await gdocs_client.append_text(doc_id, "Старая версия документа.\n")

    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="fr",
        tool_ids=["gdocs_find_replace"],
        tool_call_name="gdocs_find_replace",
        tool_call_args={
            "document_id": doc_id,
            "find": "Старая",
            "replace": "Новая",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    assert "occurrences_changed" in _tool_payloads_from_state(state)[0]
    text = await gdocs_client.read_as_text(doc_id)
    assert "Новая версия" in text
    assert "Старая" not in text


@pytest.mark.asyncio
async def test_delete_range_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    gdocs_client: GoogleDocsClient,
    di,
) -> None:
    _ = app
    doc = await gdocs_client.create_document(f"Del Target {unique_id}")
    doc_id = str(doc["documentId"])
    await gdocs_client.append_text(doc_id, "ABCDEFGHIJ")

    result, _state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="delrange",
        tool_ids=["gdocs_delete_range"],
        tool_call_name="gdocs_delete_range",
        tool_call_args={
            "document_id": doc_id,
            "start_index": 1,
            "end_index": 4,
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    text = await gdocs_client.read_as_text(doc_id)
    assert not text.startswith("ABC")


@pytest.mark.asyncio
async def test_share_anyone_via_llm_node(
    app: object,
    unique_id: str,
    mock_llm_with_queue: Any,
    gdocs_client: GoogleDocsClient,
    di,
) -> None:
    _ = app
    doc = await gdocs_client.create_document(f"Share Target {unique_id}")
    doc_id = str(doc["documentId"])

    result, state = await _run_single_tool_flow(
        unique_id,
        flow_suffix="share",
        tool_ids=["gdocs_share_document"],
        tool_call_name="gdocs_share_document",
        tool_call_args={
            "document_id": doc_id,
            "anyone": True,
            "role": "reader",
        },
        mock_llm_with_queue=mock_llm_with_queue,
        di=di,
    )
    assert result["response"] == "Готово."
    assert _tool_payloads_from_state(state)[0]["document_id"] == doc_id
