"""Состояние импорта OSM-данных.

Таблица ``geo_import_state`` — синглтон ``id=1`` (``__global_model__``).
``current_generation`` — единственное поколение, обслуживающее запросы;
своп атомарен в транзакции импортера.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoImportStatus(StrEnum):
    """Статус конвейера импорта."""

    IDLE = "idle"
    DOWNLOADING = "downloading"
    IMPORTING = "importing"
    FAILED = "failed"


class GeoImportState(PlatformModel):
    """Синглтон-строка состояния импорта и активного поколения."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_import_state"

    id: int = DbField(db_pk=True)
    current_generation: int = DbField(default=0)
    status: GeoImportStatus = DbField(default=GeoImportStatus.IDLE, max_length=32)
    source_name: str = DbField(default="", db_type="TEXT")
    source_modified_at: datetime | None = DbField(default=None)
    rows_addresses: int = DbField(default=0)
    rows_vertices: int = DbField(default=0)
    rows_edges: int = DbField(default=0)
    rows_restrictions: int = DbField(default=0)
    rows_barriers: int = DbField(default=0)
    rows_signals: int = DbField(default=0)
    last_error: str = DbField(default="", db_type="TEXT")
    started_at: datetime | None = DbField(default=None)
    finished_at: datetime | None = DbField(default=None)
    updated_at: datetime = DbField()

    @classmethod
    async def get_state(cls) -> Self | None:
        """Синглтон состояния; ``None`` до первого импорта."""
        return await cls.objects.filter(id=1).first()

    @classmethod
    async def active_generation(cls) -> int:
        """Активное поколение данных; ``0`` — справочник пуст."""
        state = await cls.get_state()
        return state.current_generation if state else 0
