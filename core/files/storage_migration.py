"""Фоновый перенос файлов компании между хранилищами."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class StorageMigrationState(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StorageMigration(PlatformModel):
    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    storage_migration_id: str = DbField(db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "storage_migrations"

    company_id: str = DbField(db_index=True)
    source_storage_id: str = DbField(db_index=True)
    target_storage_id: str = DbField()
    state: str = DbField(default=StorageMigrationState.RUNNING.value, db_index=True)
    files_total: int = DbField(default=0)
    files_moved: int = DbField(default=0)
    bytes_moved: int = DbField(default=0)
    last_error: str | None = DbField(default=None, db_type="TEXT")
    cursor: str | None = DbField(default=None)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    async def running_for_source(cls, source_storage_id: str) -> Self | None:
        rows = await (
            cls.objects.filter(
                source_storage_id=source_storage_id,
                state=StorageMigrationState.RUNNING.value,
            )
            .limit(1)
            .all()
        )
        if not rows:
            return None
        return rows[0]
