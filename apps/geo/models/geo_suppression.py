"""Тумбстоун на объект слоя кроме адреса — скрытие, переживающее импорт.

``entity`` — имя сущности и заодно ключ её OSM-id колонки:
``barrier`` → ``osm_node_id`` (geo_barriers), ``signal`` → ``osm_node_id``
(geo_traffic_signals), ``restriction`` → ``osm_relation_id``
(geo_turn_restrictions), ``edge`` → ``osm_way_id`` (geo_road_edges).
Применение — шаг ``_apply_overlays`` импортёра и мгновенное удаление
строки в живом поколении; снятие тумбстоуна возвращает объект только
со следующего импорта (в живом поколении его уже нет).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel

SUPPRESSED_ENTITIES: tuple[str, ...] = (
    "barrier",
    "signal",
    "restriction",
    "edge",
)


class GeoSuppression(PlatformModel):
    """Тумбстоун (entity, osm_id): объект скрыт из всех будущих поколений."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_suppressions"
        unique_together: list[tuple[str, str]] = [("entity", "osm_id")]

    id: int | None = DbField(default=None, db_pk=True)
    entity: str = DbField(max_length=32)
    osm_id: int = DbField(db_type="BIGINT")
    reason: str = DbField(default="", db_type="TEXT")
    updated_by: str = DbField(default="", max_length=64)
    updated_at: datetime = DbField()

    @classmethod
    async def by_object(cls, *, entity: str, osm_id: int) -> Self | None:
        """Тумбстоун по ключу (entity, osm_id)."""
        return await cls.objects.filter(entity=entity, osm_id=osm_id).first()

    @classmethod
    async def upsert_by_object(cls, item: Self) -> Self:
        """Merge по (entity, osm_id): повторный тумбстоун обновляет причину."""
        existing = await cls.by_object(entity=item.entity, osm_id=item.osm_id)
        if existing is None:
            item.updated_at = datetime.now(UTC)
            return await cls.objects.create(instance=item)
        existing.reason = item.reason
        existing.updated_by = item.updated_by
        existing.updated_at = datetime.now(UTC)
        _ = await existing.save()
        return existing

    @classmethod
    async def delete_by_object(cls, *, entity: str, osm_id: int) -> int:
        """Снятие тумбстоуна: объект вернётся со следующим поколением."""
        return await cls.objects.filter(entity=entity, osm_id=osm_id).delete()

    @classmethod
    async def list_recent_desc(cls, *, limit: int, offset: int = 0) -> list[Self]:
        """Аудит: последние тумбстоуны первыми."""
        return (
            await cls.objects.order_by("-updated_at").limit(limit).offset(offset).all()
        )
