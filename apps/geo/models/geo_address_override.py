"""Правка администратора к адресу — evergreen-оверлей над поколениями.

Админ-правки нельзя писать в ``geo_addresses``: строки пересоздаются
каждым импортом и удаляются при свопе. Override живёт отдельной таблицей
по стабильному ключу ``(osm_type, osm_id)`` и перенакатывается импортёром
на каждое новое поколение (``_apply_overlays``), а в текущем поколении
применяется сервисом мгновенно.

``before`` — JSON-снапшот исходной строки при первом override; по нему
``revert_override`` восстанавливает source-truth в живом поколении.
``suppressed`` — тумбстоун: объект скрывается из поколения и карты.
Пустой ``before`` у повторной правки не перезаписывается — снапшот всегда
хранит значения источника до первого вмешательства админа.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class GeoAddressOverride(PlatformModel):
    """Патч админа поверх адресной строки; ключ — (osm_type, osm_id)."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_address_overrides"
        unique_together: list[tuple[str, str]] = [("osm_type", "osm_id")]

    id: int | None = DbField(default=None, db_pk=True)
    osm_type: str = DbField(max_length=16)
    osm_id: int = DbField(db_type="BIGINT")
    display_name: str | None = DbField(default=None, db_type="TEXT")
    city: str | None = DbField(default=None, db_type="TEXT")
    street: str | None = DbField(default=None, db_type="TEXT")
    housenumber: str | None = DbField(default=None, db_type="TEXT")
    postcode: str | None = DbField(default=None, db_type="TEXT")
    lat: float | None = DbField(default=None)
    lng: float | None = DbField(default=None)
    suppressed: bool = DbField(default=False)
    reason: str = DbField(default="", db_type="TEXT")
    updated_by: str = DbField(default="", max_length=64)
    before: JsonObject | None = DbField(default=None, db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def by_object(cls, *, osm_type: str, osm_id: int) -> Self | None:
        """Override объекта по стабильному ключу."""
        return await cls.objects.filter(osm_type=osm_type, osm_id=osm_id).first()

    @classmethod
    async def upsert_by_object(cls, item: Self) -> Self:
        """Merge по (osm_type, osm_id); ``before`` существующего не теряется."""
        existing = await cls.by_object(osm_type=item.osm_type, osm_id=item.osm_id)
        if existing is None:
            now = datetime.now(UTC)
            item.created_at = now
            item.updated_at = now
            return await cls.objects.create(instance=item)
        if item.display_name is not None:
            existing.display_name = item.display_name
        if item.city is not None:
            existing.city = item.city
        if item.street is not None:
            existing.street = item.street
        if item.housenumber is not None:
            existing.housenumber = item.housenumber
        if item.postcode is not None:
            existing.postcode = item.postcode
        if item.lat is not None:
            existing.lat = item.lat
        if item.lng is not None:
            existing.lng = item.lng
        existing.suppressed = item.suppressed
        existing.reason = item.reason
        existing.updated_by = item.updated_by
        if item.before is not None and existing.before is None:
            existing.before = item.before
        existing.updated_at = datetime.now(UTC)
        _ = await existing.save()
        return existing

    @classmethod
    async def delete_by_object(cls, *, osm_type: str, osm_id: int) -> int:
        """Снятие override (откат к source-truth при следующем применении)."""
        return await cls.objects.filter(osm_type=osm_type, osm_id=osm_id).delete()

    @classmethod
    async def list_recent_desc(cls, *, limit: int, offset: int = 0) -> list[Self]:
        """Аудит: последние правки первыми."""
        return (
            await cls.objects.order_by("-updated_at").limit(limit).offset(offset).all()
        )

    @classmethod
    async def count_overrides(cls) -> int:
        """Число активных override (включая тумбстоуны) для аудита."""
        return await cls.objects.count()
