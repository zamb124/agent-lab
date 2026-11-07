"""Счётчики загруженных данных: поколение × источник × регион × сущность.

Таблица ``geo_stats`` (``__global_model__``). Импорт публикует точные
счётчики поколения (``set_rows`` — идемпотентно при retry в то же
поколение); строки старых поколений чистятся вместе с данными.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from core.models.platform_model import PlatformModel


class GeoStats(PlatformModel):
    """Строка счётчика сущности в поколении/регионе/источнике."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_stats"
        unique_together: list[tuple[str, str, str, str]] = [
            ("generation", "source", "region", "entity")
        ]
        indexes: list[Index] = [Index(["generation"])]

    id: int | None = DbField(default=None, db_pk=True)
    generation: int = DbField(default=0)
    source: str = DbField(max_length=64)
    region: str = DbField(default="", max_length=64)
    entity: str = DbField(max_length=64)
    rows: int = DbField(default=0, db_type="BIGINT")
    updated_at: datetime = DbField()

    @classmethod
    async def set_rows(
        cls,
        *,
        generation: int,
        source: str,
        region: str,
        entity: str,
        rows: int,
    ) -> None:
        """Точный счётчик ключа; повтор в то же поколение — перезапись."""
        now = datetime.now(UTC)
        _ = await execute_raw(
            """
            INSERT INTO geo_stats (generation, source, region, entity, rows, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (generation, source, region, entity)
            DO UPDATE SET rows = EXCLUDED.rows, updated_at = EXCLUDED.updated_at
            """,
            [generation, source, region, entity, rows, now],
            using="geo",
        )

    @classmethod
    async def list_for_generation_by_source_region_entity_asc(cls, generation: int) -> list[Self]:
        """Все счётчики поколения по source/region/entity."""
        return (
            await cls.objects.filter(generation=generation)
            .order_by("source", "region", "entity")
            .all()
        )

    @classmethod
    async def list_for_overview_by_source_region_entity_asc(cls, generation: int) -> list[Self]:
        """Счётчики обзора: активное поколение плюс evergreen-строки (gen0).

        Источники обогащения (ГАР и др.) пишут счётчики с ``generation=0`` —
        они не умирают со свопом и должны быть видны в обзоре всегда.
        """
        return (
            await cls.objects.filter(generation__in=[0, generation])
            .order_by("source", "region", "entity")
            .all()
        )
