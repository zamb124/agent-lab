"""Планировщик форматирования Markdown для заметок."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_schedule_note_markdown_format_skips_when_feature_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_settings = MagicMock()
    mock_settings.note_attachment_markdown_format_enabled = False
    monkeypatch.setattr(
        "apps.crm.services.note_markdown_format_schedule.get_crm_settings",
        lambda: mock_settings,
    )
    from apps.crm.services.note_markdown_format_schedule import schedule_note_markdown_format

    await schedule_note_markdown_format(
        note_id="note-1",
        company_id="company-1",
        namespace="default",
        expected_updated_at_iso="2026-05-10T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_schedule_note_markdown_format_skips_without_context(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_settings = MagicMock()
    mock_settings.note_attachment_markdown_format_enabled = True
    monkeypatch.setattr(
        "apps.crm.services.note_markdown_format_schedule.get_crm_settings",
        lambda: mock_settings,
    )
    monkeypatch.setattr("apps.crm.services.note_markdown_format_schedule.get_context", lambda: None)
    from apps.crm.services.note_markdown_format_schedule import schedule_note_markdown_format

    await schedule_note_markdown_format(
        note_id="note-1",
        company_id="company-1",
        namespace="default",
        expected_updated_at_iso="2026-05-10T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_enqueue_note_markdown_format_task_requires_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("apps.crm.services.note_markdown_format_schedule.get_context", lambda: None)
    from apps.crm.services.note_markdown_format_schedule import enqueue_note_markdown_format_task

    with pytest.raises(ValueError, match="контекст"):
        await enqueue_note_markdown_format_task(
            note_id="note-1",
            company_id="company-1",
            namespace="default",
            expected_updated_at_iso="2026-05-10T12:00:00+00:00",
        )
