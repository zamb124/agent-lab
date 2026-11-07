"""Правка администратора к дороге (way) — закрытие режимов движения.

``cost_masks`` — JSONB ``{"car": true, "foot": true, ...}``: какие режимы
выключены на всех рёбрах этого way. Применение выставляет ``-1`` в
соответствующих ``*_cost``/``*_reverse_cost`` колонках живого поколения и
перенакатывается импортёром (``_apply_overlays``) на каждое новое. Снятие
правки возвращает стоимости только со следующим импортом — исходные
значения не сохраняются (поколения и так хранят исходную правду
источника).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel
from core.types import JsonObject

OVERRIDABLE_MODES: tuple[str, ...] = ("car", "foot", "bike", "scooter")


class GeoEdgeOverride(PlatformModel):
    """Закрытие режимов движения на OSM way; ключ — osm_way_id."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_edge_overrides"

    id: int | None = DbField(default=None, db_pk=True)
    osm_way_id: int = DbField(db_type="BIGINT", unique=True)
    cost_masks: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    reason: str = DbField(default="", db_type="TEXT")
    updated_by: str = DbField(default="", max_length=64)
    updated_at: datetime = DbField()

    @classmethod
    async def by_way(cls, *, osm_way_id: int) -> Self | None:
        """Правка way по ключу."""
        return await cls.objects.filter(osm_way_id=osm_way_id).first()

    @classmethod
    async def upsert_by_way(cls, item: Self) -> Self:
        """Merge по osm_way_id."""
        existing = await cls.by_way(osm_way_id=item.osm_way_id)
        if existing is None:
            item.updated_at = datetime.now(UTC)
            return await cls.objects.create(instance=item)
        existing.cost_masks = item.cost_masks
        existing.reason = item.reason
        existing.updated_by = item.updated_by
        existing.updated_at = datetime.now(UTC)
        _ = await existing.save()
        return existing

    @classmethod
    async def delete_by_way(cls, *, osm_way_id: int) -> int:
        """Снятие правки: стоимости восстановятся со следующим импортом."""
        return await cls.objects.filter(osm_way_id=osm_way_id).delete()

    @classmethod
    async def list_recent_desc(cls, *, limit: int, offset: int = 0) -> list[Self]:
        """Аудит: последние правки дорог первыми."""
        return (
            await cls.objects.order_by("-updated_at").limit(limit).offset(offset).all()
        )
