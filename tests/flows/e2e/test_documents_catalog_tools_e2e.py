"""E2E: Documents catalog builtins over real Office + Files + Flows (no ServiceClient ASGI patch).

Covers deep nested catalogs, real uploaded files, every tool and every find mode.
"""

from __future__ import annotations

import ast
import asyncio
import io
import json
from typing import Any, cast

import pytest
from a2a.helpers.proto_helpers import get_message_text
from a2a.types import Message
from docx import Document
from fastapi import FastAPI

from apps.flows.di import FlowsDi
from apps.flows.src.durable_execution import RunStartedPayload, WorkflowEventType
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from apps.flows.src.state import ExecutionState
from apps.flows.src.streaming import InMemoryEmitter
from apps.flows.tools.documents.documents_catalog import (
    documents_find,
    documents_get_link,
    documents_list_catalog,
    documents_read,
)
from core.a2a import mapping_from_struct
from core.context import clear_context, set_context
from core.di import require_di
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.types import JsonObject, require_json_object
from tests.flows.durable_runtime_harness import ensure_workflow_started
from tests.office.helpers import upload_office_file_bytes

pytestmark = [
    pytest.mark.real_taskiq,
    pytest.mark.timeout(180, func_only=True),
    pytest.mark.usefixtures("frontend_service", "office_service"),
]

# Minimal valid 1x1 PNG (BFF image preview returns file URL).
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _headers(auth_headers_system: dict[str, str]) -> dict[str, str]:
    return {**auth_headers_system, "X-Platform-Namespace": "default"}


def _docx_bytes(*paragraphs: str) -> bytes:
    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _tool_state(*, unique_id: str, system_user_id: str) -> ExecutionState:
    return ExecutionState.create(
        task_id=f"docs-catalog-e2e-{unique_id}",
        context_id=f"ctx-docs-catalog-{unique_id}",
        user_id=system_user_id,
        session_id=f"docs-catalog-e2e:ctx-{unique_id}",
    )


def _catalog_ids(payload: JsonObject) -> set[str]:
    items = payload["catalogs"]
    assert isinstance(items, list)
    out: set[str] = set()
    for item in items:
        obj = require_json_object(item, "catalogs.item")
        catalog_id = obj["catalog_id"]
        assert isinstance(catalog_id, str)
        out.add(catalog_id)
    return out


def _file_ids(payload: JsonObject, key: str = "documents") -> set[str]:
    items = payload[key]
    assert isinstance(items, list)
    out: set[str] = set()
    for item in items:
        obj = require_json_object(item, f"{key}.item")
        file_id = obj["file_id"]
        assert isinstance(file_id, str)
        out.add(file_id)
    return out


async def _create_catalog(
    office_client_http,
    headers: dict[str, str],
    *,
    title: str,
    parent_catalog_id: str | None = None,
) -> str:
    body: dict[str, object] = {"title": title, "is_public": False}
    if parent_catalog_id is not None:
        body["parent_catalog_id"] = parent_catalog_id
    response = await office_client_http.post(
        "/documents/api/v1/catalogs",
        headers=headers,
        json=body,
    )
    assert response.status_code == 200, response.text
    catalog_id = response.json()["catalog_id"]
    assert isinstance(catalog_id, str) and catalog_id
    return catalog_id


async def _upload_document(
    office_client_http,
    headers: dict[str, str],
    *,
    catalog_id: str,
    title: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> str:
    uploaded = await upload_office_file_bytes(
        office_client_http,
        headers,
        filename=filename,
        content=content,
        content_type=content_type,
    )
    file_id = uploaded["file_id"]
    if not isinstance(file_id, str) or file_id == "":
        raise AssertionError("_upload_document: file_id required")
    bind = await office_client_http.post(
        "/documents/api/v1/documents",
        headers=headers,
        json={"file_id": file_id, "title": title, "catalog_id": catalog_id},
    )
    assert bind.status_code == 200, bind.text
    bound_file_id = bind.json()["file_id"]
    assert isinstance(bound_file_id, str) and bound_file_id
    return bound_file_id


async def _enable_rag_index(
    office_client_http,
    headers: dict[str, str],
    catalog_id: str,
) -> None:
    response = await office_client_http.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/enable",
        headers=headers,
    )
    assert response.status_code == 200, response.text


async def _wait_rag_document_completed(
    rag_client,
    headers: dict[str, str],
    file_id: str,
    *,
    max_wait: float = 90.0,
) -> None:
    elapsed = 0.0
    interval = 0.25
    while elapsed < max_wait:
        status_response = await rag_client.get(
            f"/rag/api/v1/documents/{file_id}/status",
            headers=headers,
        )
        assert status_response.status_code == 200, status_response.text
        status_data = status_response.json()
        if status_data["status"] == "completed":
            return
        if status_data["status"] == "failed":
            pytest.fail(str(status_data.get("error_message")))
        await asyncio.sleep(interval)
        elapsed += interval
    pytest.fail(f"RAG document {file_id} did not complete within {max_wait}s")


async def _wait_catalog_index_ready(
    office_client_http,
    headers: dict[str, str],
    catalog_id: str,
    *,
    ready_count: int,
    max_wait: float = 90.0,
) -> None:
    elapsed = 0.0
    interval = 0.25
    while elapsed < max_wait:
        status_response = await office_client_http.get(
            f"/documents/api/v1/catalogs/{catalog_id}/rag-index/status",
            headers=headers,
        )
        assert status_response.status_code == 200, status_response.text
        totals = status_response.json()["totals"]
        assert isinstance(totals, dict)
        if int(totals["failed"]) > 0:
            pytest.fail(f"catalog RAG indexing failed: {totals}")
        if int(totals["ready"]) >= ready_count and int(totals["pending"]) == 0:
            return
        await asyncio.sleep(interval)
        elapsed += interval
    pytest.fail(f"catalog {catalog_id} index not ready={ready_count} within {max_wait}s")


@pytest.fixture
def documents_catalog_runtime_context(
    auth_token_system: str,
    system_user_id: str,
):
    ctx = Context(
        user=User(user_id=system_user_id, name="Documents catalog e2e"),
        active_company=Company(company_id="system", name="System"),
        auth_token=auth_token_system,
        channel="test",
        active_namespace="default",
        metadata={"user_id": system_user_id},
    )
    set_context(ctx)
    try:
        yield ctx
    finally:
        clear_context()


@pytest.mark.asyncio
@pytest.mark.no_service_client_patch
async def test_documents_catalog_tools_deep_tree_all_modes(
    documents_catalog_runtime_context,
    office_client_http,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system: dict[str, str],
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = documents_catalog_runtime_context, rag_service, rag_worker
    headers = _headers(auth_headers_system)
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)

    # Deep tree: L0 → L1 → L2 → L3 (4 levels).
    l0 = await _create_catalog(
        office_client_http, headers, title=f"L0-root-{unique_id}"
    )
    l1 = await _create_catalog(
        office_client_http, headers, title=f"L1-{unique_id}", parent_catalog_id=l0
    )
    l2 = await _create_catalog(
        office_client_http, headers, title=f"L2-{unique_id}", parent_catalog_id=l1
    )
    l3 = await _create_catalog(
        office_client_http, headers, title=f"L3-leaf-{unique_id}", parent_catalog_id=l2
    )

    leaf_marker = f"LEAF_BODY_{unique_id}"
    leaf_title = f"LeafReport {unique_id}"
    leaf_file_id = await _upload_document(
        office_client_http,
        headers,
        catalog_id=l3,
        title=leaf_title,
        filename=f"leaf-{unique_id}.txt",
        content=f"{leaf_marker}\nsecond line\n".encode("utf-8"),
        content_type="text/plain",
    )

    mid_title = f"MidDocx {unique_id}"
    mid_marker = f"MID_DOCX_{unique_id}"
    mid_file_id = await _upload_document(
        office_client_http,
        headers,
        catalog_id=l2,
        title=mid_title,
        filename=f"mid-{unique_id}.docx",
        content=_docx_bytes(f"Paragraph with {mid_marker}"),
        content_type=DOCX_MIME,
    )

    image_title = f"PreviewPng {unique_id}"
    image_file_id = await _upload_document(
        office_client_http,
        headers,
        catalog_id=l1,
        title=image_title,
        filename=f"preview-{unique_id}.png",
        content=_PNG_1X1,
        content_type="image/png",
    )

    decoy_title = f"DecoyRoot {unique_id}"
    decoy_file_id = await _upload_document(
        office_client_http,
        headers,
        catalog_id=l0,
        title=decoy_title,
        filename=f"decoy-{unique_id}.txt",
        content=b"decoy only\n",
        content_type="text/plain",
    )

    # --- documents_list_catalog: root + non-recursive levels ---
    root = require_json_object(
        await documents_list_catalog.run({}, state),
        "list.root",
    )
    root_catalogs = _catalog_ids(root)
    assert l0 in root_catalogs
    assert l1 not in root_catalogs
    assert l2 not in root_catalogs
    assert l3 not in root_catalogs
    assert root["documents"] == []

    at_l0 = require_json_object(
        await documents_list_catalog.run({"catalog_id": l0}, state),
        "list.l0",
    )
    assert _catalog_ids(at_l0) == {l1}
    assert _file_ids(at_l0) == {decoy_file_id}

    at_l1 = require_json_object(
        await documents_list_catalog.run({"catalog_id": l1}, state),
        "list.l1",
    )
    assert _catalog_ids(at_l1) == {l2}
    assert _file_ids(at_l1) == {image_file_id}

    at_l2 = require_json_object(
        await documents_list_catalog.run({"catalog_id": l2}, state),
        "list.l2",
    )
    assert _catalog_ids(at_l2) == {l3}
    assert _file_ids(at_l2) == {mid_file_id}

    at_l3 = require_json_object(
        await documents_list_catalog.run({"catalog_id": l3}, state),
        "list.l3",
    )
    assert _catalog_ids(at_l3) == set()
    assert _file_ids(at_l3) == {leaf_file_id}

    # --- documents_find: lexical scoped / global / auto / semantic-disabled ---
    lexical_scoped = require_json_object(
        await documents_find.run(
            {"query": leaf_title, "catalog_id": l3, "mode": "lexical"},
            state,
        ),
        "find.lexical_scoped",
    )
    assert lexical_scoped["mode_used"] == "lexical"
    assert _file_ids(lexical_scoped, "items") == {leaf_file_id}

    lexical_global = require_json_object(
        await documents_find.run(
            {"query": leaf_title, "mode": "lexical"},
            state,
        ),
        "find.lexical_global",
    )
    assert leaf_file_id in _file_ids(lexical_global, "items")

    auto_before_rag = require_json_object(
        await documents_find.run(
            {"query": leaf_title, "catalog_id": l3, "mode": "auto"},
            state,
        ),
        "find.auto_before_rag",
    )
    assert auto_before_rag["mode_used"] == "lexical"
    assert leaf_file_id in _file_ids(auto_before_rag, "items")

    with pytest.raises(ValueError, match="rag_index_disabled"):
        await documents_find.run(
            {"query": leaf_marker, "catalog_id": l3, "mode": "semantic"},
            state,
        )

    with pytest.raises(ValueError, match="catalog_id_required"):
        await documents_find.run(
            {"query": leaf_marker, "mode": "semantic"},
            state,
        )

    # --- documents_find: semantic + auto after real catalog RAG index ---
    await _enable_rag_index(office_client_http, headers, l3)
    await _wait_catalog_index_ready(
        office_client_http, headers, l3, ready_count=1
    )
    await _wait_rag_document_completed(rag_client, headers, leaf_file_id)

    semantic_ok = require_json_object(
        await documents_find.run(
            {"query": leaf_marker, "catalog_id": l3, "mode": "semantic"},
            state,
        ),
        "find.semantic_ok",
    )
    assert semantic_ok["mode_used"] == "semantic"
    assert leaf_file_id in _file_ids(semantic_ok, "items")

    auto_after_rag = require_json_object(
        await documents_find.run(
            {"query": leaf_marker, "catalog_id": l3, "mode": "auto"},
            state,
        ),
        "find.auto_after_rag",
    )
    assert auto_after_rag["mode_used"] == "semantic"
    assert leaf_file_id in _file_ids(auto_after_rag, "items")

    # --- documents_read: file_id ---
    read_leaf = require_json_object(
        await documents_read.run({"file_id": leaf_file_id}, state),
        "read.leaf",
    )
    assert read_leaf["file_id"] == leaf_file_id
    assert leaf_marker in str(read_leaf["envelope"])

    read_file = require_json_object(
        await documents_read.run({"file_id": mid_file_id}, state),
        "read.file_id",
    )
    assert read_file["file_id"] == mid_file_id
    assert mid_marker in str(read_file["envelope"])

    # --- documents_get_link: editor + preview ---
    editor = require_json_object(
        await documents_get_link.run(
            {"file_id": leaf_file_id, "kind": "editor"},
            state,
        ),
        "link.editor",
    )
    assert editor["kind"] == "editor"
    assert f"/documents/edit/{leaf_file_id}" in str(editor["url"])
    assert "namespace=default" in str(editor["url"])

    preview_image = require_json_object(
        await documents_get_link.run(
            {"file_id": image_file_id, "kind": "preview"},
            state,
        ),
        "link.preview_image",
    )
    assert preview_image["kind"] == "preview"
    assert isinstance(preview_image["url"], str) and preview_image["url"].strip() != ""

    with pytest.raises(ValueError, match="preview"):
        await documents_get_link.run(
            {"file_id": leaf_file_id, "kind": "preview"},
            state,
        )


def _message_plain_text(message: Message) -> str:
    return get_message_text(message)


def _json_object_from_tool_result(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return cast(dict[str, Any], raw)
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed_json = json.loads(raw)
    except json.JSONDecodeError:
        parsed_json = None
    if isinstance(parsed_json, dict):
        return cast(dict[str, Any], parsed_json)
    try:
        parsed_literal = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return None
    if isinstance(parsed_literal, dict):
        return cast(dict[str, Any], parsed_literal)
    return None


def _successful_tool_payloads_from_messages(state: ExecutionState) -> list[dict[str, Any]]:
    """Успешные tool results из A2A messages (metadata.tool_call_id); tool_results ключует по имени тула."""
    payloads: list[dict[str, Any]] = []
    for message in state.messages:
        if not isinstance(message, Message):
            continue
        if not message.HasField("metadata"):
            continue
        metadata = mapping_from_struct(message.metadata)
        if "tool_call_id" not in metadata:
            continue
        parsed = _json_object_from_tool_result(_message_plain_text(message))
        if parsed is not None:
            payloads.append(parsed)
    return payloads


@pytest.mark.asyncio
@pytest.mark.no_service_client_patch
async def test_llm_node_runner_documents_catalog_tools(
    app,
    documents_catalog_runtime_context,
    office_client_http,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
    unique_id: str,
    system_user_id: str,
) -> None:
    """llm_node + MockLLM in-process; tools hit real Office/Files HTTP (no ServiceClient ASGI patch)."""
    _ = documents_catalog_runtime_context
    assert isinstance(app, FastAPI)
    headers = _headers(auth_headers_system)
    l0 = await _create_catalog(
        office_client_http, headers, title=f"runner-L0-{unique_id}"
    )
    l1 = await _create_catalog(
        office_client_http, headers, title=f"runner-L1-{unique_id}", parent_catalog_id=l0
    )
    l2 = await _create_catalog(
        office_client_http, headers, title=f"runner-L2-{unique_id}", parent_catalog_id=l1
    )
    marker = f"RUNNER_CATALOG_{unique_id}"
    title = f"RunnerLeaf {unique_id}"
    file_id = await _upload_document(
        office_client_http,
        headers,
        catalog_id=l2,
        title=title,
        filename=f"runner-leaf-{unique_id}.txt",
        content=f"{marker}\n".encode("utf-8"),
        content_type="text/plain",
    )

    flow_id = f"docs_catalog_runner_{unique_id}"
    mock_llm = mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "documents_list_catalog",
                "args": {"catalog_id": l0},
            },
            {
                "type": "tool_call",
                "tool": "documents_list_catalog",
                "args": {"catalog_id": l1},
            },
            {
                "type": "tool_call",
                "tool": "documents_find",
                "args": {"query": title, "catalog_id": l2, "mode": "lexical"},
            },
            {
                "type": "tool_call",
                "tool": "documents_read",
                "args": {"file_id": file_id, "page_end": 0, "budget": 4000},
            },
            {
                "type": "tool_call",
                "tool": "documents_get_link",
                "args": {"file_id": file_id, "kind": "editor"},
            },
            {
                "type": "text",
                "content": f"done {file_id}",
            },
        ]
    )

    node_config = NodeConfig(
        node_id=f"catalog_node_{unique_id}",
        type=NodeType.LLM_NODE,
        name="Documents catalog runner",
        description="",
        prompt="Browse nested Documents catalogs with catalog tools.",
        tools=[],
        llm=NodeLLMConfig(provider="mock", model="mock-gpt-4"),
    )
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    state.session_id = f"{flow_id}:{state.context_id}"
    state.content = "browse catalogs"

    di = require_di(app, FlowsDi)
    _ = await di.workflow_runtime.save_state(
        state.session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )
    await ensure_workflow_started(
        di=di,
        state=state,
        flow_id=flow_id,
        branch_id=state.branch_id,
    )
    runner = LlmNodeRunner(
        node_config=node_config,
        tools=[
            documents_list_catalog,
            documents_find,
            documents_read,
            documents_get_link,
        ],
        llm=mock_llm,
        prompt="Browse nested Documents catalogs with catalog tools.",
        workflow_runtime=di.node_constructor.workflow_runtime, memory_store=di.node_constructor.llm_context_memory_store, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, redis_client=di.node_constructor.redis_client, tool_registry=di.tool_registry,
    )
    async for _ in runner.run({"content": "browse catalogs"}, state, InMemoryEmitter(state)):
        pass

    payloads = _successful_tool_payloads_from_messages(state)
    assert payloads, f"no successful tool messages: {state.messages}"

    listed_l0 = any(
        payload.get("catalog_id") == l0 and l1 in _catalog_ids(payload)
        for payload in payloads
        if "catalogs" in payload
    )
    listed_l1 = any(
        payload.get("catalog_id") == l1 and l2 in _catalog_ids(payload)
        for payload in payloads
        if "catalogs" in payload
    )
    found_leaf = any(
        payload.get("mode_used") == "lexical"
        and file_id in _file_ids(payload, "items")
        for payload in payloads
        if "items" in payload
    )
    read_leaf = any(
        payload.get("file_id") == file_id and marker in str(payload.get("envelope"))
        for payload in payloads
        if "envelope" in payload
    )
    linked = any(
        payload.get("kind") == "editor" and file_id in str(payload.get("url"))
        for payload in payloads
        if payload.get("kind") == "editor"
    )
    assert listed_l0, payloads
    assert listed_l1, payloads
    assert found_leaf, payloads
    assert read_leaf, payloads
    assert linked, payloads
