"""Регион покрытия геоданных: город, область или произвольный bbox.

Таблица ``geo_regions`` (``__global_model__``). Регион — единица
управления покрытием: «добавить город» — новая строка со своим bbox и
экстрактами; импорт помечает строки данных её ``name``. Полигон ``geom``
— GENERATED ALWAYS ``ST_MakeEnvelope`` в миграции, в модели не объявлен.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import execute_raw

from core.models.platform_model import PlatformModel


class GeoRegionKind(StrEnum):
    """Тип региона покрытия."""

    CITY = "city"
    REGION = "region"
    CUSTOM = "custom"


class GeoRegion(PlatformModel):
    """Строка реестра покрытия: bbox, экстракты, флаг активности."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_regions"

    id: int | None = DbField(default=None, db_pk=True)
    name: str = DbField(max_length=64, unique=True)
    title: str = DbField(default="", max_length=255)
    kind: GeoRegionKind = DbField(default=GeoRegionKind.CUSTOM, max_length=32)
    bbox_south: float = DbField()
    bbox_west: float = DbField()
    bbox_north: float = DbField()
    bbox_east: float = DbField()
    extract_urls: list[str] = DbField(default_factory=list, db_type="JSONB")
    replication_url: str = DbField(default="", db_type="TEXT")
    enabled: bool = DbField(default=True)
    last_imported_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    def bbox_tuple(self) -> tuple[float, float, float, float]:
        """``(lat_min, lng_min, lat_max, lng_max)`` — формат ``coverage_bbox``."""
        return (self.bbox_south, self.bbox_west, self.bbox_north, self.bbox_east)

    @classmethod
    async def by_name(cls, name: str) -> Self | None:
        """Регион по slug-имени; ``None`` при отсутствии."""
        return await cls.objects.filter(name=name).first()

    @classmethod
    async def list_all_by_name_asc(cls) -> list[Self]:
        """Все регионы по имени."""
        return await cls.objects.order_by("name").all()

    @classmethod
    async def list_enabled_by_name_asc(cls) -> list[Self]:
        """Активные регионы — участники синхронизации."""
        return await cls.objects.filter(enabled=True).order_by("name").all()

    @classmethod
    async def delete_by_pk(cls, region_id: int) -> bool:
        """Удаление по int-PK; ``True`` — строка существовала."""
        deleted = await cls.objects.filter(id=region_id).delete()
        return deleted > 0

    @classmethod
    async def insert_once(cls, instance: Self) -> bool:
        """Вставка при отсутствии по ``name``; ``True`` — строка создана."""
        rows = await execute_raw(
            """
            INSERT INTO geo_regions
                (name, title, kind, bbox_south, bbox_west, bbox_north,
                 bbox_east, extract_urls, replication_url, enabled,
                 created_at, updated_at)
            VALUES ($1, $2, $3::geo_region_kind_enum, $4, $5, $6, $7,
                    $8::jsonb, $9, $10, $11, $11)
            ON CONFLICT (name) DO NOTHING
            RETURNING id
            """,
            [
                instance.name,
                instance.title,
                instance.kind.value,
                instance.bbox_south,
                instance.bbox_west,
                instance.bbox_north,
                instance.bbox_east,
                json.dumps(instance.extract_urls),
                instance.replication_url,
                instance.enabled,
                datetime.now(UTC),
            ],
            using="geo",
        )
        return len(rows) > 0

    @classmethod
    async def mark_imported(cls, names: list[str]) -> None:
        """``last_imported_at`` регионам прошедшего импорта."""
        if not names:
            return
        now = datetime.now(UTC)
        _ = await cls.objects.filter(name__in=names).update(
            last_imported_at=now, updated_at=now
        )
