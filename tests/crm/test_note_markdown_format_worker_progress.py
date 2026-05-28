"""Форматирование Markdown заметки: один вызов TextTransformService, финальный WS."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest import MonkeyPatch

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from tests.crm.e2e._json_helpers import object_dict, object_str

FormatMarkdownTaskFn = Callable[..., Awaitable[dict[str, object]]]


@pytest.mark.asyncio
async def test_note_markdown_format_single_text_transform_call_full_body(
    monkeypatch: MonkeyPatch,
) -> None:
    from apps.crm_worker.tasks import note_markdown_tasks as nmt

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(nmt, "set_crm_context", _noop)

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

    def _passthrough_update(entity: object) -> object:
        return entity

    repo = MagicMock()
    repo.get = AsyncMock(return_value=note_ent)
    repo.update = AsyncMock(side_effect=_passthrough_update)

    container = MagicMock()
    container.entity_repository = repo
    container.company_repository = MagicMock()
    container.access_grant_repository = MagicMock()
    monkeypatch.setattr(nmt, "get_crm_container", lambda: container)

    class _TextTransformSettings:
        markdown_max_chunk_chars: int = 6000

    class _Settings:
        text_transforms: _TextTransformSettings = _TextTransformSettings()

    monkeypatch.setattr(nmt, "get_settings", lambda: _Settings())

    format_calls: list[dict[str, str]] = []

    class _TextTransformService:
        async def format_markdown(self, text: str) -> str:
            format_calls.append({"text": text})
            return "# ok\n"

    monkeypatch.setattr(nmt, "TextTransformService", _TextTransformService)

    broadcast_calls: list[dict[str, object]] = []

    async def _broadcast(**kwargs: object) -> None:
        broadcast_calls.append(dict(kwargs))

    monkeypatch.setattr(nmt, "broadcast_crm_note_event", _broadcast)

    raw_fn = cast(
        FormatMarkdownTaskFn,
        inspect.unwrap(nmt.format_note_description_markdown_task),
    )
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
    assert object_str(cast(object, note_ent.description), field="description") == "# ok"
    assert len(broadcast_calls) == 1
    first_broadcast = broadcast_calls[0]
    assert first_broadcast["skip_notification_center"] is False
    markdown_format = object_dict(
        first_broadcast.get("markdown_format"),
        field="markdown_format",
    )
    assert markdown_format["phase"] == "complete"
    assert markdown_format["chunks_done"] == 1
    assert markdown_format["chunks_total"] == 1
