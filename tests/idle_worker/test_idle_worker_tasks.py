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
from core.files.create_spec import FileSourceKind
from core.files.file_repository import FileRepository
from core.files.models import FileRecord, FileStatus
from core.files.registry import default_retention_for_source


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
    purged_count = result["purged_count"]
    failed_count = result["failed_count"]
    assert isinstance(purged_count, int)
    assert isinstance(failed_count, int)
    assert purged_count >= 0
    assert failed_count >= 0


@pytest.mark.asyncio
async def test_file_retention_backfill_tick_skips_empty_repository(
    frontend_container,
    unique_id: str,
) -> None:
    """Backfill тик исполняется на shared БД и возвращает корректную структуру."""
    result = await file_retention_tasks.file_retention_backfill_tick(
        schedule_task_id=f"backfill_{unique_id}",
        company_id=None,
    )

    assert set(result.keys()) == {"scanned", "updated", "skipped"}
    assert result["scanned"] >= 0
    assert result["updated"] >= 0
    assert result["skipped"] >= 0


@pytest.mark.asyncio
async def test_file_retention_backfill_tick_updates_record_missing_retention(
    frontend_container,
    unique_id: str,
) -> None:
    """Backfill обновляет FileRecord без retention, заполняя его по source_kind."""
    repository: FileRepository = frontend_container.file_repository
    retention = default_retention_for_source(FileSourceKind.FLOW_SESSION)

    company_id = f"co_backfill_{unique_id}"
    file_id = f"file_backfill_{unique_id}"
    record = FileRecord(
        file_id=file_id,
        provider="minio",
        original_name=f"backfill_{unique_id}.txt",
        s3_key=f"test-bucket/backfill_{unique_id}",
        s3_bucket="test-bucket",
        content_type="text/plain",
        file_size=10,
        checksum=f"sha256_{unique_id}",
        status=FileStatus.UPLOADED,
        company_id=company_id,
        metadata={"source_kind": FileSourceKind.FLOW_SESSION.value},
    )
    saved = await repository.set(record)
    assert saved is True
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

        refreshed = await repository.get(file_id)
        assert refreshed is not None
        assert refreshed.retention_kind == retention.kind
    finally:
        await repository.delete(file_id)


# --- platform_schedules_gc + redis_inventory (без container injection) -------


@pytest.mark.asyncio
async def test_platform_schedules_gc_tick_runs_against_real_redis(
    unique_id: str,
) -> None:
    """GC orphan keys тик на реальном TaskIQ broker Redis возвращает структуру."""
    from apps.idle_worker.tasks.platform_schedules_gc_tasks import (
        platform_schedules_gc_tick,
    )

    result = await platform_schedules_gc_tick(
        schedule_task_id=f"gc_{unique_id}",
        company_id=None,
    )

    assert isinstance(result, dict)
    assert "scanned_keys" in result
    assert "deleted_orphans" in result
    assert "orphan_samples" in result
    assert isinstance(result["scanned_keys"], int)
    assert isinstance(result["deleted_orphans"], int)
    assert isinstance(result["orphan_samples"], list)


@pytest.mark.asyncio
async def test_redis_inventory_tick_reports_db_sizes(unique_id: str) -> None:
    """Redis inventory тик возвращает dbsize/no_ttl метрики для domain и broker Redis."""
    from apps.idle_worker.tasks.redis_inventory_tasks import redis_inventory_tick

    result = await redis_inventory_tick(
        schedule_task_id=f"inv_{unique_id}",
        company_id=None,
    )

    assert isinstance(result, dict)
    assert "domain_dbsize" in result
    assert "broker_dbsize" in result
    assert "domain_no_ttl_total" in result
    assert "broker_no_ttl_total" in result
    assert "duration_ms" in result
    assert isinstance(result["domain_dbsize"], int)
    assert isinstance(result["broker_dbsize"], int)
    assert result["duration_ms"] >= 0
