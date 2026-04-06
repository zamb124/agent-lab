"""
Сквозная проверка Lara CRM tools: JSON с blocks для embed-чата (без реального HTTP).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.flows.tools.lara_crm import crm_analyze_note_text, crm_create_note
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User


@pytest.fixture
def crm_context() -> Context:
    ctx = Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace="default",
    )
    set_context(ctx)
    yield ctx
    clear_context()


@pytest.mark.asyncio
async def test_crm_create_note_tool_returns_blocks_for_chat(
    crm_context: Context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.flows.src.tools.decorator.is_test_mode", lambda: False)

    mock_client = MagicMock()

    async def post(service: str, path: str, **kwargs: object) -> dict:
        assert service == "crm"
        assert path == "/api/v1/entities"
        return {"entity_id": "note_e2e_1", "name": "Title", "entity_type": "note"}

    mock_client.post = AsyncMock(side_effect=post)
    monkeypatch.setattr("apps.flows.tools.lara_crm.ServiceClient", lambda: mock_client)

    state = MagicMock()
    raw = await crm_create_note.run({"name": "Title", "description": "Body"}, state)
    data = json.loads(raw)
    assert data["success"] is True
    assert data["entity_id"] == "note_e2e_1"
    assert isinstance(data["blocks"], list)
    types = {b.get("type") for b in data["blocks"]}
    assert "card" in types
    assert "actions" in types


@pytest.mark.asyncio
async def test_crm_analyze_note_text_tool_returns_blocks_for_chat(
    crm_context: Context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.flows.src.tools.decorator.is_test_mode", lambda: False)

    mock_client = MagicMock()

    async def post(service: str, path: str, **kwargs: object) -> dict:
        assert "analyze" in path
        return {"entities": [{"entity_id": "x"}]}

    mock_client.post = AsyncMock(side_effect=post)
    monkeypatch.setattr("apps.flows.tools.lara_crm.ServiceClient", lambda: mock_client)

    state = MagicMock()
    raw = await crm_analyze_note_text.run(
        {"text": "hello", "note_id": "nid1"},
        state,
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert isinstance(data["blocks"], list)
    assert any(b.get("type") == "actions" for b in data["blocks"])
