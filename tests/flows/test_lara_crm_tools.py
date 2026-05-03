"""
Интеграционные тесты Lara CRM tools: реальный ServiceClient -> CRM HTTP (9003), без monkeypatch.

Вызов _run_impl обходит decorator mock при TESTING=true.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from apps.flows.tools.lara_crm import (
    crm_analyze_note_text,
    crm_create_note,
    crm_create_note_and_analyze,
    crm_search_entities,
)
from core.state import ExecutionState

pytestmark = [
    pytest.mark.timeout(120, func_only=True),
    pytest.mark.xdist_group("real_taskiq"),
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


@pytest.mark.asyncio
async def test_crm_create_note_tool_returns_blocks_for_chat(
    crm_service,
    crm_client,
    lara_crm_tool_context,
    unique_id: str,
    system_user_id: str,
) -> None:
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    propose_raw = await crm_create_note._run_impl(
        {"name": f"Lara note {unique_id}", "description": "Тело заметки для теста тула.", "mode": "propose"},
        state,
    )
    proposed = json.loads(propose_raw)
    pending_events = getattr(state, "ui_events_pending")
    assert pending_events[-1]["type"] == "action_previewed"
    preview_buttons = pending_events[-1]["payload"]["blocks"][1]["buttons"]
    assert preview_buttons[0]["action_kind"] == "apply"
    assert preview_buttons[0]["action_id"] == "crm.note.create.apply"
    raw = await crm_create_note._run_impl(
        {
            "name": f"Lara note {unique_id}",
            "description": "Тело заметки для теста тула.",
            "mode": "apply",
            "pending_action_id": proposed["pending_action_id"],
        },
        state,
    )
    data = json.loads(raw)
    assert data["success"] is True, f"crm_create_note failed: {data}"
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

    # Вектор для поиска пишется в RAG с namespace_id=default (entity_repository.create).
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
    data = json.loads(raw)
    assert data["success"] is True, f"crm_search_entities failed: {data}"
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
    import asyncio
    import time

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
    await mock_llm_redis([_slot, _slot])

    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    create_propose_raw = await crm_create_note._run_impl(
        {
            "name": note_title,
            "description": "Текст заметки для AI-анализа.",
            "mode": "propose",
        },
        state,
    )
    create_proposed = json.loads(create_propose_raw)
    create_raw = await crm_create_note._run_impl(
        {
            "name": note_title,
            "description": "Текст заметки для AI-анализа.",
            "mode": "apply",
            "pending_action_id": create_proposed["pending_action_id"],
        },
        state,
    )
    created = json.loads(create_raw)
    assert created["success"] is True
    note_id = created["entity_id"]
    assert isinstance(note_id, str) and note_id

    start_resp = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json={
            "note_id": note_id,
            "check_duplicates": False,
            "include_attachments": False,
        },
        headers=auth_headers_system,
    )
    assert start_resp.status_code == 202, start_resp.text
    task_id = start_resp.json()["task_id"]
    deadline = time.monotonic() + 60.0
    last: dict = {}
    while time.monotonic() < deadline:
        tr = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=auth_headers_system)
        last = tr.json()
        if last.get("status") in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    assert last.get("status") == "completed", f"task failed: {last.get('error_message')}"

    task_data = last.get("data")
    if not isinstance(task_data, dict):
        raise AssertionError(f"task response missing data dict: {last!r}")
    entities_done = task_data.get("result_entities_count")
    assert isinstance(entities_done, int) and entities_done >= 1, (
        f"ожидались извлечённые сущности в задаче analyze, получено result_entities_count={entities_done!r}, "
        f"task={last!r}"
    )

    entity_resp = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
    draft = entity_resp.json().get("attributes", {}).get("ai_analysis_draft") or {}
    entities = draft.get("entities") or []
    assert len(entities) >= 1


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
    import asyncio
    import time

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
    await mock_llm_redis([_combo_slot, _combo_slot])

    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    create_propose_raw = await crm_create_note._run_impl(
        {
            "name": note_title,
            "description": "Полный текст для создания и анализа.",
            "mode": "propose",
        },
        state,
    )
    create_proposed = json.loads(create_propose_raw)
    create_raw = await crm_create_note._run_impl(
        {
            "name": note_title,
            "description": "Полный текст для создания и анализа.",
            "mode": "apply",
            "pending_action_id": create_proposed["pending_action_id"],
        },
        state,
    )
    created = json.loads(create_raw)
    assert created["success"] is True
    note_id = created["entity_id"]
    assert isinstance(note_id, str) and note_id

    start_resp = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json={
            "note_id": note_id,
            "check_duplicates": False,
            "include_attachments": False,
        },
        headers=auth_headers_system,
    )
    assert start_resp.status_code == 202, start_resp.text
    task_id = start_resp.json()["task_id"]
    deadline = time.monotonic() + 60.0
    last: dict = {}
    while time.monotonic() < deadline:
        tr = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=auth_headers_system)
        last = tr.json()
        if last.get("status") in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    assert last.get("status") == "completed", f"task failed: {last.get('error_message')}"

    task_data_combo = last.get("data")
    if not isinstance(task_data_combo, dict):
        raise AssertionError(f"task response missing data dict: {last!r}")
    entities_done_combo = task_data_combo.get("result_entities_count")
    assert isinstance(entities_done_combo, int) and entities_done_combo >= 1, (
        f"ожидались извлечённые сущности в задаче analyze, получено result_entities_count={entities_done_combo!r}, "
        f"task={last!r}"
    )

    entity_resp = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
    draft = entity_resp.json().get("attributes", {}).get("ai_analysis_draft") or {}
    entities = draft.get("entities") or []
    assert len(entities) >= 1
