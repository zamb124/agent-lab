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

pytestmark = pytest.mark.timeout(120, func_only=True)


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

    ns = f"g_{unique_id}"
    ctx = Context(
        user=User(user_id=system_user_id, name="Lara CRM tools"),
        active_company=Company(company_id="system", name="System"),
        auth_token=auth_token_system,
        channel="test",
        active_namespace=ns,
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
    raw = await crm_create_note._run_impl(
        {"name": f"Lara note {unique_id}", "description": "Тело заметки для теста тула."},
        state,
    )
    data = json.loads(raw)
    assert data["success"] is True
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
    assert data["success"] is True
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
) -> None:
    note_title = f"Lara analyze {unique_id}"
    await mock_llm_redis(
        [
            {
                "type": "text",
                "content": json.dumps(
                    {
                        "note": {
                            "entity_type": "note",
                            "name": note_title,
                            "description": "Краткое содержание для анализа.",
                        },
                        "entities": [
                            {
                                "entity_type": "task",
                                "name": f"Задача {unique_id}",
                                "description": "Проверка извлечения сущности",
                            }
                        ],
                        "relationships": [],
                        "metadata": {
                            "dates_mentioned": [],
                            "places_mentioned": [],
                            "key_topics": [],
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )

    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    create_raw = await crm_create_note._run_impl(
        {
            "name": note_title,
            "description": "Текст заметки для AI-анализа.",
        },
        state,
    )
    created = json.loads(create_raw)
    assert created["success"] is True
    note_id = created["entity_id"]
    assert isinstance(note_id, str) and note_id

    raw = await crm_analyze_note_text._run_impl(
        {"text": "Текст заметки для AI-анализа.", "note_id": note_id},
        state,
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert isinstance(data["blocks"], list)
    assert any(b.get("type") == "actions" for b in data["blocks"])
    analyze = data.get("analyze")
    assert isinstance(analyze, dict)
    entities = analyze.get("entities")
    assert isinstance(entities, list)
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
) -> None:
    note_title = f"Lara combo {unique_id}"
    await mock_llm_redis(
        [
            {
                "type": "text",
                "content": json.dumps(
                    {
                        "note": {
                            "entity_type": "note",
                            "name": note_title,
                            "description": "Комбо: заметка и анализ.",
                        },
                        "entities": [
                            {
                                "entity_type": "contact",
                                "name": f"Контакт {unique_id}",
                                "description": "Извлечённый контакт",
                            }
                        ],
                        "relationships": [],
                        "metadata": {
                            "dates_mentioned": [],
                            "places_mentioned": [],
                            "key_topics": [],
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )

    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    raw = await crm_create_note_and_analyze._run_impl(
        {
            "name": note_title,
            "description": "Полный текст для создания и анализа.",
        },
        state,
    )
    data = json.loads(raw)
    assert data["success"] is True
    eid = data.get("entity_id")
    assert isinstance(eid, str) and eid
    analyze = data.get("analyze")
    assert isinstance(analyze, dict)
    entities = analyze.get("entities")
    assert isinstance(entities, list)
    assert len(entities) >= 1
