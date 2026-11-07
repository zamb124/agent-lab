"""Курсор чанкового импорта источника: позиция для resume после падения.

Таблица ``geo_source_cursors`` (``__global_model__``). Одна строка на
пару ``(source, region)``: краулер пишет opaque-``cursor`` (offset,
page, last id) после каждого чанка, рестарт продолжает с него, а не с
нуля.
"""

from __future__ import annotations

from datetime import UTC, datetime
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

    @classmethod
    async def upsert_progress(
        cls,
        *,
        source: str,
        region: str,
        cursor: str,
        rows_done: int,
        status: GeoCursorStatus = GeoCursorStatus.RUNNING,
        last_error: str = "",
    ) -> Self:
        """Запись прогресса чанка: merge по (source, region)."""
        existing = await cls.by_source_region(source, region)
        now = datetime.now(UTC)
        if existing is None:
            return await cls.objects.create(
                instance=cls(
                    source=source,
                    region=region,
                    cursor=cursor,
                    status=status,
                    rows_done=rows_done,
                    last_error=last_error,
                    updated_at=now,
                )
            )
        existing.cursor = cursor
        existing.status = status
        existing.rows_done = rows_done
        existing.last_error = last_error
        existing.updated_at = now
        _ = await existing.save()
        return existing

    @classmethod
    async def reset_for(cls, *, source: str, region: str) -> Self | None:
        """Сброс прогресса: следующий тик проходит поток заново.

        Строка сохраняется для наблюдаемости; ``None`` — курсор не найден.
        """
        existing = await cls.by_source_region(source, region)
        if existing is None:
            return None
        existing.cursor = ""
        existing.status = GeoCursorStatus.IDLE
        existing.rows_done = 0
        existing.last_error = ""
        existing.updated_at = datetime.now(UTC)
        _ = await existing.save()
        return existing

    @classmethod
    async def mark_failed(cls, *, source: str, region: str, error: str) -> None:
        """Фиксация падения потока: курсор остаётся для resume."""
        existing = await cls.by_source_region(source, region)
        if existing is None:
            _ = await cls.objects.create(
                instance=cls(
                    source=source,
                    region=region,
                    status=GeoCursorStatus.FAILED,
                    last_error=error,
                    updated_at=datetime.now(UTC),
                )
            )
            return
        existing.status = GeoCursorStatus.FAILED
        existing.last_error = error
        existing.updated_at = datetime.now(UTC)
        _ = await existing.save()
