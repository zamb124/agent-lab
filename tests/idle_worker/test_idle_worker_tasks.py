"""Direct in-process тесты TaskIQ tick-задач idle_worker.

Tick-функции в ``apps/idle_worker/tasks/*`` запускаются worker-процессом через
``make test-up`` и не инструментируются coverage. Эти тесты вызывают tick-функции
напрямую, подставляя реальный ``frontend_container`` через ``set_container`` —
официальный DI API для тестов (не monkeypatch).

Покрытие: ``file_retention_purge_tick``, ``file_retention_backfill_tick``.
"""

from __future__ import annotations

import pytest

from apps.idle_worker.container import reset_container, set_container
from apps.idle_worker.tasks import file_retention_tasks
from core.files.file_repository import FileRepository
from core.files.registry import default_retention_for_source
from core.files.create_spec import FileSourceKind


@pytest.fixture(autouse=True)
def _bind_idle_container(frontend_container):
    """Подставляет реальный frontend container в idle_worker registry на время теста."""
    set_container(frontend_container)
    yield
    reset_container()


@pytest.mark.asyncio
async def test_file_retention_purge_tick_returns_zero_when_disabled(
    frontend_container,
) -> None:
    """Purge выключен через ``files.retention.purge_enabled=false`` → no-op."""
    from core.config import get_settings

    settings = get_settings()
    original = settings.files.retention.purge_enabled
    settings.files.retention.purge_enabled = False
    try:
        result = await file_retention_tasks.file_retention_purge_tick(
            schedule_task_id="test-schedule-id",
            company_id=None,
        )
    finally:
        settings.files.retention.purge_enabled = original

    assert result == {"purged_count": 0, "failed_count": 0}


@pytest.mark.asyncio
async def test_file_retention_purge_tick_runs_batch_without_failures(
    frontend_container,
    unique_id: str,
) -> None:
    """Purge тик исполняет ``purge_expired_batch`` на пустой shared БД без ошибок."""
    from core.config import get_settings

    settings = get_settings()
    original = settings.files.retention.purge_enabled
    settings.files.retention.purge_enabled = True
    try:
        result = await file_retention_tasks.file_retention_purge_tick(
            schedule_task_id=f"purge_{unique_id}",
            company_id=None,
        )
    finally:
        settings.files.retention.purge_enabled = original

    assert isinstance(result, dict)
    assert "purged_count" in result
    assert "failed_count" in result
    assert result["purged_count"] >= 0
    assert result["failed_count"] >= 0


@pytest.mark.asyncio
async def test_file_retention_backfill_tick_skips_empty_repository(
    frontend_container,
    unique_id: str,
) -> None:
    """Backfill тик на пустом репозитории возвращает нули и не падает."""
    result = await file_retention_tasks.file_retention_backfill_tick(
        schedule_task_id=f"backfill_{unique_id}",
        company_id=None,
    )

    assert result == {"scanned": 0, "updated": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_file_retention_backfill_tick_updates_record_missing_retention(
    frontend_container,
    unique_id: str,
) -> None:
    """Backfill обновляет FileRecord без retention, заполняя его по source_kind."""
    repository: FileRepository = frontend_container.file_repository
    retention = default_retention_for_source(FileSourceKind.FLOW_ATTACHMENT)

    record = await repository.create(
        company_id=f"co_backfill_{unique_id}",
        original_name=f"backfill_{unique_id}.txt",
        content_type="text/plain",
        file_size=10,
        checksum=f"sha256_{unique_id}",
        storage_url=f"s3://test-bucket/backfill_{unique_id}",
        metadata={"source_kind": FileSourceKind.FLOW_ATTACHMENT.value},
    )
    try:
        from core.config import get_settings

        settings = get_settings()
        original = settings.files.retention.backfill_batch_size
        settings.files.retention.backfill_batch_size = 100
        try:
            result = await file_retention_tasks.file_retention_backfill_tick(
                schedule_task_id=f"backfill_{unique_id}",
                company_id=None,
            )
        finally:
            settings.files.retention.backfill_batch_size = original

        assert result["scanned"] >= 1
        assert result["updated"] >= 1

        refreshed = await repository.get(record.file_id)
        assert refreshed is not None
        assert refreshed.retention_kind == retention.kind
    finally:
        await repository.delete(record.file_id)
