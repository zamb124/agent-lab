"""Планировщик форматирования Markdown для заметок."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _schedule_dependencies() -> dict[str, MagicMock]:
    return {"authz": MagicMock()}


@pytest.mark.asyncio
async def test_schedule_note_markdown_format_skips_when_feature_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_settings = MagicMock()
    mock_settings.note_attachment_markdown_format_enabled = False
    monkeypatch.setattr(
        "apps.crm.services.note_markdown_format_schedule.get_crm_settings",
        lambda: mock_settings,
    )
    from apps.crm.services.note_markdown_format_schedule import schedule_note_markdown_format

    out = await schedule_note_markdown_format(
        **_schedule_dependencies(),
        note_id="note-1",
        company_id="company-1",
        namespace="default",
    )
    assert out is False


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

    out = await schedule_note_markdown_format(
        **_schedule_dependencies(),
        note_id="note-1",
        company_id="company-1",
        namespace="default",
    )
    assert out is False


@pytest.mark.asyncio
async def test_schedule_note_markdown_format_coalesces_active_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.crm.services.note_markdown_format_schedule import ActiveTaskExistsError

    mock_settings = MagicMock()
    mock_settings.note_attachment_markdown_format_enabled = True
    monkeypatch.setattr(
        "apps.crm.services.note_markdown_format_schedule.get_crm_settings",
        lambda: mock_settings,
    )
    mock_context = MagicMock()
    mock_context.auth_token = "token"
    monkeypatch.setattr(
        "apps.crm.services.note_markdown_format_schedule.get_context",
        lambda: mock_context,
    )

    async def _raise_active(*_args: object, **_kwargs: object) -> None:
        raise ActiveTaskExistsError("note_markdown_format", "task-1", dedup={"note_id": "note-1"})

    monkeypatch.setattr(
        "apps.crm.services.note_markdown_format_schedule.begin_note_markdown_format",
        _raise_active,
    )
    from apps.crm.services.note_markdown_format_schedule import schedule_note_markdown_format

    out = await schedule_note_markdown_format(
        authz=MagicMock(),
        note_id="note-1",
        company_id="company-1",
        namespace="default",
    )
    assert out is False


@pytest.mark.asyncio
async def test_enqueue_note_markdown_format_task_requires_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise_context(*_args: object, **_kwargs: object) -> None:
        raise ValueError("Request context is required to start note formatting")

    monkeypatch.setattr(
        "apps.crm.services.note_markdown_format_schedule.begin_note_markdown_format",
        _raise_context,
    )
    from apps.crm.services.note_markdown_format_schedule import enqueue_note_markdown_format_task

    with pytest.raises(ValueError, match="context"):
        _ = await enqueue_note_markdown_format_task(
            authz=MagicMock(),
            note_id="note-1",
            company_id="company-1",
            namespace="default",
        )
