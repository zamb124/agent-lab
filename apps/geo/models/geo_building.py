"""Здание — evergreen-контур с кадастровым номером (НСПД и др.).

Здания не зависят от OSM-поколений: контур приходит из НСПД/Росреестра и
обновляется in-place, поэтому поколения у таблицы нет. ``geom``
(GENERATED из ``geojson``) — каноническая пространственная колонка;
``geojson`` хранится текстом, как ``zone`` у зон доставки. Ключ —
``cadastral_number`` (уникален).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoBuilding(PlatformModel):
    """Контур здания; ключ — cadastral_number."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_buildings"

    id: int | None = DbField(default=None, db_pk=True)
    cadastral_number: str = DbField(max_length=32, unique=True)
    address: str = DbField(default="", db_type="TEXT")
    lat: float = DbField()
    lng: float = DbField()
    geojson: str = DbField(default="", db_type="TEXT")
    region: str = DbField(default="", db_index=True, max_length=64)
    source: str = DbField(default="", db_type="TEXT")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def by_cadastral_number(cls, *, cadastral_number: str) -> Self | None:
        """Здание по кадастровому номеру."""
        return (
            await cls.objects.filter(cadastral_number=cadastral_number).first()
        )

    @classmethod
    async def count_for_region(cls, region: str) -> int:
        """Число зданий региона (для geo_stats)."""
        return await cls.objects.filter(region=region).count()

    @classmethod
    async def upsert_by_cadastral_number(cls, item: Self) -> Self:
        """Merge по cadastral_number."""
        existing = await cls.by_cadastral_number(
            cadastral_number=item.cadastral_number
        )
        if existing is None:
            now = datetime.now(UTC)
            item.created_at = now
            item.updated_at = now
            return await cls.objects.create(instance=item)
        existing.address = item.address
        existing.lat = item.lat
        existing.lng = item.lng
        existing.geojson = item.geojson
        existing.region = item.region
        existing.source = item.source
        existing.updated_at = datetime.now(UTC)
        _ = await existing.save()
        return existing
