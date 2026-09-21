"""
Интеграционные тесты Lara CRM tools: реальный ServiceClient -> CRM HTTP, без monkeypatch.

Вызов _run_impl обходит decorator mock при TESTING=true.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from apps.flows.tools.crm.crm_tools import (
    crm_analyze_note_text,
    crm_create_note,
    crm_create_note_and_analyze,
    crm_search_entities,
)
from core.flow_ui.document import FlowUIActionPreview, FlowUIButton
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, require_json_object
from tests.flows._flow_ui import conversation_blocks

pytestmark = [
    pytest.mark.timeout(120, func_only=True),
]


@pytest_asyncio.fixture
async def lara_crm_tool_context(
    crm_client,
    auth_token_system,
    system_user_id,
    unique_id,
):
    from core.context import set_context
    from core.models.context_models import Context
    from core.models.identity_models import Company, User

    _ = crm_client
    _ = unique_id
    ctx = Context(
        user=User(user_id=system_user_id, name="Lara CRM tools"),
        active_company=Company(company_id="system", name="System"),
        auth_token=auth_token_system,
        channel="test",
        active_namespace="default",
        metadata={"user_id": system_user_id, "email": "test@example.com", "grps": []},
    )
    set_context(ctx)
    return ctx


def _tool_state(*, unique_id: str, system_user_id: str) -> ExecutionState:
    return ExecutionState.create(
        task_id=f"lara-tool-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id=system_user_id,
        session_id=f"lara:ctx-{unique_id}",
    )


def _as_object(raw: JsonValue) -> JsonObject:
    if isinstance(raw, str):
        return require_json_object(json.loads(raw), "crm.tool.result")
    return require_json_object(raw, "crm.tool.result")


@pytest.mark.asyncio
async def test_crm_create_note_tool_returns_blocks_for_chat(
    crm_service,
    crm_client,
    lara_crm_tool_context,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = crm_service
    _ = crm_client
    _ = lara_crm_tool_context
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    propose_raw = await crm_create_note._run_impl(
        {
            "name": f"Lara note {unique_id}",
            "description": "Тело заметки для теста тула.",
            "mode": "propose",
        },
        state,
    )
    proposed = _as_object(propose_raw)
    preview, apply_button = conversation_blocks(state)[-2:]
    assert isinstance(preview, FlowUIActionPreview)
    assert preview.block_id.startswith("crm-note-preview-")
    assert isinstance(apply_button, FlowUIButton)
    assert apply_button.action is not None
    assert apply_button.action.name == "apply_pending_action"
    assert apply_button.action.payload["capability"] == "crm.note"
    raw = await crm_create_note._run_impl(
        {
            "mode": "apply",
            "pending_action_id": proposed["pending_action_id"],
        },
        state,
    )
    data = _as_object(raw)
    assert isinstance(data.get("entity_id"), str) and data["entity_id"]
    assert isinstance(data["blocks"], list)
    types = {b.get("type") for b in data["blocks"]}
    assert "card" in types
    assert "actions" in types


@pytest.mark.asyncio
async def test_crm_search_entities_tool(
    crm_service,
    crm_client,
    lara_crm_tool_context,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict,
) -> None:
    from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit

    _ = crm_service
    _ = lara_crm_tool_context
    marker = f"lara_tool_search_marker_{unique_id}"
    create = await crm_client.post(
        "/crm/api/v1/entities",
        json={
            "entity_type": "organization",
            "name": f"Org {unique_id}",
            "description": f"Описание для семантики. {marker} " + ("context " * 40),
            "namespace": "default",
        },
        headers=auth_headers_system,
    )
    assert create.status_code in (200, 201), create.text

    await wait_for_crm_semantic_search_hit(
        crm_client,
        auth_headers_system,
        query=marker,
        entity_type="organization",
        namespace="default",
    )

    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    raw = await crm_search_entities._run_impl(
        {"query": marker, "entity_type": "organization", "namespace": "default", "limit": 5},
        state,
    )
    data = _as_object(raw)
    assert len(data["hits"]) >= 1
    hit = data["hits"][0]
    assert hit.get("entity_id")
    desc = hit.get("description")
    if isinstance(desc, str) and len(desc) > 400:
        assert desc.endswith("…")
    assert any(b.get("type") == "table" for b in data["blocks"])


@pytest.mark.real_taskiq
@pytest.mark.asyncio
async def test_crm_analyze_note_text_tool_returns_blocks_for_chat(
    crm_service,
    crm_client,
    lara_crm_tool_context,
    unique_id: str,
    system_user_id: str,
    mock_llm_redis,
    auth_headers_system: dict,
) -> None:
    _ = crm_service
    _ = crm_client
    _ = lara_crm_tool_context
    _ = auth_headers_system
    note_title = f"Lara analyze {unique_id}"
    _analyze_body = {
        "note": {
            "entity_type": "note",
            "name": note_title,
            "description": "Краткое содержание для анализа.",
            "attributes": {},
            "confidence": 0.9,
        },
        "entities": [
            {
                "entity_type": "contact",
                "name": f"Контакт {unique_id}",
                "description": "Проверка извлечения сущности для Lara analyze",
                "attributes": {},
                "confidence": 0.85,
            }
        ],
        "relationships": [],
        "metadata": {
            "dates_mentioned": [],
            "places_mentioned": [],
            "key_topics": [],
        },
        "attachment_summaries": [],
    }
    _slot = {
        "type": "text",
        "content": json.dumps(_analyze_body, ensure_ascii=False),
    }
    await mock_llm_redis([_slot, _slot, _slot, _slot, _slot, _slot])

    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    create_propose_raw = await crm_create_note._run_impl(
        {
            "name": note_title,
            "description": "Текст заметки для AI-анализа.",
            "mode": "propose",
        },
        state,
    )
    create_proposed = _as_object(create_propose_raw)
    create_raw = await crm_create_note._run_impl(
        {
            "mode": "apply",
            "pending_action_id": create_proposed["pending_action_id"],
        },
        state,
    )
    created = _as_object(create_raw)
    note_id = created["entity_id"]
    assert isinstance(note_id, str) and note_id

    analyze_raw = await crm_analyze_note_text._run_impl({"note_id": note_id}, state)
    analyzed = _as_object(analyze_raw)
    blocks_out = analyzed.get("blocks")
    assert isinstance(blocks_out, list) and len(blocks_out) >= 1

    ao = analyzed.get("analyze")
    assert isinstance(ao, dict), analyzed
    task_data_preview = ao.get("result_entities_count")
    entities_tool = ao.get("entities") or []
    assert isinstance(entities_tool, list) and len(entities_tool) >= 1, analyzed
    if task_data_preview is not None:
        assert isinstance(task_data_preview, int) and task_data_preview >= 1, analyzed


@pytest.mark.real_taskiq
@pytest.mark.asyncio
async def test_crm_create_note_and_analyze_tool_chains(
    crm_service,
    crm_client,
    lara_crm_tool_context,
    unique_id: str,
    system_user_id: str,
    mock_llm_redis,
    auth_headers_system: dict,
) -> None:
    _ = crm_service
    _ = crm_client
    _ = lara_crm_tool_context
    _ = auth_headers_system
    note_title = f"Lara combo {unique_id}"
    _combo_body = {
        "note": {
            "entity_type": "note",
            "name": note_title,
            "description": "Комбо: заметка и анализ.",
            "attributes": {},
            "confidence": 0.9,
        },
        "entities": [
            {
                "entity_type": "contact",
                "name": f"Контакт {unique_id}",
                "description": "Извлечённый контакт",
                "attributes": {},
                "confidence": 0.87,
            }
        ],
        "relationships": [],
        "metadata": {
            "dates_mentioned": [],
            "places_mentioned": [],
            "key_topics": [],
        },
        "attachment_summaries": [],
    }
    _combo_slot = {
        "type": "text",
        "content": json.dumps(_combo_body, ensure_ascii=False),
    }
    # create+analyze + background daily-summary rebuild share the same test_scope queue
    await mock_llm_redis(
        [_combo_slot, _combo_slot, _combo_slot, _combo_slot, _combo_slot, _combo_slot]
    )

    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    combo_raw = await crm_create_note_and_analyze._run_impl(
        {
            "name": note_title,
            "description": "Полный текст для создания и анализа.",
        },
        state,
    )
    combo = _as_object(combo_raw)
    note_id = combo["entity_id"]
    assert isinstance(note_id, str) and note_id
    ao = combo.get("analyze")
    assert isinstance(ao, dict), combo
    entities_combo = ao.get("entities") or []
    assert isinstance(entities_combo, list) and len(entities_combo) >= 1, combo

    cnt = ao.get("result_entities_count")
    if cnt is not None:
        assert isinstance(cnt, int) and cnt >= 1, combo
