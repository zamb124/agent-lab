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


def _note(*, description: str) -> SimpleNamespace:
    return SimpleNamespace(
        entity_id="note-1",
        company_id="co-1",
        namespace="default",
        entity_type=NOTE_ROOT_ENTITY_TYPE_ID,
        description=description,
        updated_at=datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
        note_date=datetime(2026, 1, 9, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_note_markdown_format_single_text_transform_call_full_body(
    monkeypatch: MonkeyPatch,
) -> None:
    from apps.crm_worker.tasks import note_markdown_tasks as nmt

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(nmt, "set_crm_context", _noop)

    full_text = "alpha\n\n" * 800
    note_ent = _note(description=full_text)

    async def _apply_description(
        entity_id: str,
        *,
        expected_description: str,
        description: str,
    ) -> SimpleNamespace:
        assert entity_id == "note-1"
        assert expected_description == full_text
        note_ent.description = description
        return note_ent

    repo = MagicMock()
    repo.get = AsyncMock(return_value=note_ent)
    repo.update_description_if_current = AsyncMock(side_effect=_apply_description)
    repo.update = AsyncMock()

    container = MagicMock()
    container.entity_repository = repo
    container.company_repository = MagicMock()
    container.authz_service = MagicMock()
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
    )

    assert result["status"] == "completed"
    assert len(format_calls) == 1
    assert format_calls[0]["text"] == full_text.strip()
    assert object_str(cast(object, note_ent.description), field="description") == "# ok"
    repo.update.assert_not_called()
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


@pytest.mark.asyncio
async def test_note_markdown_format_skips_when_description_changed(
    monkeypatch: MonkeyPatch,
) -> None:
    from apps.crm_worker.tasks import note_markdown_tasks as nmt

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(nmt, "set_crm_context", _noop)

    note_before = _note(description="hello")

    repo = MagicMock()
    repo.get = AsyncMock(return_value=note_before)
    repo.update_description_if_current = AsyncMock(return_value=None)
    repo.update = AsyncMock()

    container = MagicMock()
    container.entity_repository = repo
    container.company_repository = MagicMock()
    container.authz_service = MagicMock()
    monkeypatch.setattr(nmt, "get_crm_container", lambda: container)

    class _TextTransformSettings:
        markdown_max_chunk_chars: int = 6000

    class _Settings:
        text_transforms: _TextTransformSettings = _TextTransformSettings()

    monkeypatch.setattr(nmt, "get_settings", lambda: _Settings())

    class _TextTransformService:
        async def format_markdown(self, text: str) -> str:
            _ = text
            return "# ok\n"

    monkeypatch.setattr(nmt, "TextTransformService", _TextTransformService)
    monkeypatch.setattr(nmt, "broadcast_crm_note_event", AsyncMock())

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
    )

    assert result["status"] == "skipped_stale"
    repo.update.assert_not_called()
    repo.update_description_if_current.assert_awaited_once()
