"""События объектного хранилища на шине platform:events."""

from __future__ import annotations

from pydantic import BaseModel

from core.events import register_platform_event

STORAGE_MIGRATION_PROGRESSED = "frontend/company_storage_migration/progressed"


class StorageMigrationProgressedPayload(BaseModel):
    storage_migration_id: str
    state: str
    files_total: int
    files_moved: int
    bytes_moved: int
    last_error: str | None = None


register_platform_event(
    STORAGE_MIGRATION_PROGRESSED,
    StorageMigrationProgressedPayload,
    description="Прогресс переноса файлов компании между хранилищами",
)
