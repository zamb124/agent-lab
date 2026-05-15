"""Форматирование Markdown заметки: один вызов TextTransformService, финальный WS."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID


@pytest.mark.asyncio
async def test_note_markdown_format_single_text_transform_call_full_body(monkeypatch: pytest.MonkeyPatch) -> None:
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
    settings_mock.provider_litserve.infra.markdown_max_chunk_chars = 6000
    monkeypatch.setattr(nmt, "get_settings", lambda: settings_mock)

    format_calls: list[dict[str, Any]] = []

    class _TextTransformService:
        async def format_markdown(
            self,
            text: str,
            *,
            max_chunk_chars: int | None = None,
            **_kwargs: Any,
        ) -> str:
            format_calls.append({"text": text, "max_chunk_chars": max_chunk_chars})
            return "# ok\n"

    monkeypatch.setattr(nmt, "TextTransformService", _TextTransformService)

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
    assert len(format_calls) == 1
    assert format_calls[0]["text"] == full_text.strip()
    assert format_calls[0]["max_chunk_chars"] == 6000
    assert note_ent.description == "# ok"
    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["skip_notification_center"] is False
    assert broadcast_calls[0]["markdown_format"]["phase"] == "complete"
    assert broadcast_calls[0]["markdown_format"]["chunks_done"] == 1
    assert broadcast_calls[0]["markdown_format"]["chunks_total"] == 1
