"""Батч переноса файлов компании между хранилищами."""

from __future__ import annotations

from apps.idle.tasks.task_names import TASK_STORAGE_MIGRATION_TICK
from core.events import publish_event_to_company
from core.files.events import STORAGE_MIGRATION_PROGRESSED
from core.files.storage_migration import StorageMigrationState
from core.files.storage_move import run_storage_migration_batch
from core.logging import get_logger
from core.tasks import enqueue, platform_task

logger = get_logger(__name__)


@platform_task(TASK_STORAGE_MIGRATION_TICK)
async def storage_migration_tick(storage_migration_id: str) -> dict[str, str | int]:
    migration = await run_storage_migration_batch(storage_migration_id)
    await publish_event_to_company(
        migration.company_id,
        STORAGE_MIGRATION_PROGRESSED,
        {
            "storage_migration_id": migration.storage_migration_id,
            "state": migration.state,
            "files_total": migration.files_total,
            "files_moved": migration.files_moved,
            "bytes_moved": migration.bytes_moved,
            "last_error": migration.last_error,
        },
    )
    logger.info(
        "idle.storage_migration_tick",
        storage_migration_id=migration.storage_migration_id,
        state=migration.state,
        files_moved=migration.files_moved,
    )
    if migration.state == StorageMigrationState.RUNNING.value:
        _ = await enqueue(TASK_STORAGE_MIGRATION_TICK, storage_migration_id=storage_migration_id)
    return {
        "storage_migration_id": migration.storage_migration_id,
        "state": migration.state,
        "files_moved": migration.files_moved,
    }
