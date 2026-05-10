"""Форматирование Markdown заметки: один вызов LitServe на весь текст, финальный WS."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID


@pytest.mark.asyncio
async def test_note_markdown_format_single_litserve_call_full_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.crm_worker.tasks import note_markdown_tasks as nmt

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(nmt, "_set_crm_context", _noop)

    fixed_dt = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    full_text = "alpha\n\n" * 800

    note_ent = SimpleNamespace(
        entity_id="note-1",
        company_id="co-1",
        namespace="default",
        entity_type=NOTE_ROOT_ENTITY_TYPE_ID,
        description=full_text,
        updated_at=fixed_dt,
        note_date=datetime(2026, 1, 9, tzinfo=timezone.utc),
    )

    repo = MagicMock()
    repo.get = AsyncMock(return_value=note_ent)
    repo.update = AsyncMock(side_effect=lambda e: e)

    container = MagicMock()
    container.entity_repository = repo
    container.company_repository = MagicMock()
    container.access_grant_repository = MagicMock()
    monkeypatch.setattr(nmt, "get_crm_container", lambda: container)

    settings_mock = MagicMock()
    settings_mock.note_markdown_format_service_timeout_seconds = 120.0
    settings_mock.provider_litserve.infra.markdown_default_api_model_id = "test-model"
    settings_mock.provider_litserve.infra.markdown_max_chunk_chars = 6000
    monkeypatch.setattr(nmt, "get_settings", lambda: settings_mock)

    post_calls: list[dict[str, Any]] = []

    async def _post(
        _service: str,
        _path: str,
        *,
        json: dict[str, Any],
        timeout: float,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        post_calls.append(dict(json))
        return {
            "markdown": "# ok\n",
            "chunks_total": 5,
            "chunks_processed": 5,
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=_post)
    monkeypatch.setattr(nmt, "ServiceClient", lambda: mock_client)

    broadcast_calls: list[dict[str, Any]] = []

    async def _broadcast(**kwargs: Any) -> None:
        broadcast_calls.append(kwargs)

    monkeypatch.setattr(nmt, "broadcast_crm_note_event", _broadcast)

    raw_fn = inspect.unwrap(nmt.format_note_description_markdown_task)
    result = await raw_fn(
        "note-1",
        "co-1",
        "default",
        "tok",
        "user-1",
        "ru",
        fixed_dt.isoformat(),
    )

    assert result["status"] == "completed"
    assert len(post_calls) == 1
    assert post_calls[0]["text"] == full_text.strip()
    assert post_calls[0]["model"] == "test-model"
    assert post_calls[0]["max_chunk_chars"] == 6000
    assert note_ent.description == "# ok"
    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["skip_notification_center"] is False
    assert broadcast_calls[0]["markdown_format"]["phase"] == "complete"
    assert broadcast_calls[0]["markdown_format"]["chunks_done"] == 5
    assert broadcast_calls[0]["markdown_format"]["chunks_total"] == 5
