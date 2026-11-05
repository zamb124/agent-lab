"""Курсор чанкового импорта источника: позиция для resume после падения.

Таблица ``geo_source_cursors`` (``__global_model__``). Одна строка на
пару ``(source, region)``: краулер пишет opaque-``cursor`` (offset,
page, last id) после каждого чанка, рестарт продолжает с него, а не с
нуля.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoCursorStatus(StrEnum):
    """Состояние потока импорта по курсору."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class GeoSourceCursor(PlatformModel):
    """Позиция и статус чанкового потока источника."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_source_cursors"
        unique_together: list[tuple[str, str]] = [("source", "region")]

    id: int | None = DbField(default=None, db_pk=True)
    source: str = DbField(max_length=64)
    region: str = DbField(default="", max_length=64)
    cursor: str = DbField(default="", db_type="TEXT")
    status: GeoCursorStatus = DbField(default=GeoCursorStatus.IDLE, max_length=32)
    rows_done: int = DbField(default=0, db_type="BIGINT")
    last_error: str = DbField(default="", db_type="TEXT")
    updated_at: datetime = DbField()

    @classmethod
    async def by_source_region(cls, source: str, region: str) -> Self | None:
        """Курсор потока; ``None`` — источник ещё не запускался."""
        return await cls.objects.filter(source=source, region=region).first()

    @classmethod
    async def list_all_by_source_region_asc(cls) -> list[Self]:
        """Все курсоры по источнику."""
        return await cls.objects.order_by("source", "region").all()
