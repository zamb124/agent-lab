"""Импорт заметки amoCRM не падает, если анализ этой заметки уже запущен."""

import pytest

from apps.crm.integrations.amocrm.service import start_imported_note_analyze
from apps.crm.models.api import NoteProcessingConfig
from apps.crm.models.task import CRMTask
from apps.crm.services.note_markdown_format_schedule import ActiveTaskExistsError


class _AlreadyRunning:
    def __init__(self) -> None:
        self.calls: int = 0

    async def start_note_analyze(
        self,
        *,
        note_id: str,
        note_name: str,
        namespace: str,
        mode: str,
        config: NoteProcessingConfig,
    ) -> CRMTask:
        _ = note_name, namespace, mode, config
        self.calls += 1
        raise ActiveTaskExistsError(
            "note_analyze",
            "task-existing",
            dedup={"note_id": note_id},
        )


@pytest.mark.asyncio
async def test_start_imported_note_analyze_keeps_import_when_task_exists() -> None:
    starter = _AlreadyRunning()
    await start_imported_note_analyze(
        starter,
        note_id="note-1",
        note_name="Amo примечание",
        namespace="sales",
    )
    assert starter.calls == 1
