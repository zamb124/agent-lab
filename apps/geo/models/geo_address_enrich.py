"""Атрибуты адреса от источников обогащения (ГАР, НСПД).

Строка привязана к стабильному OSM-ключу ``(osm_type, osm_id)`` и поэтому
переживает своп поколения: импортёр переносит атрибуты в колонки
``geo_addresses`` шагом ``_apply_overlays``. Колонки зеркалят
соответствующие поля адреса; здесь лежит каноническое «до правки админа»
значение — админ-override имеет приоритет и сюда не пишется.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import execute_raw

from core.models.platform_model import PlatformModel
from core.types import SqlParameterValue


class GeoAddressEnrich(PlatformModel):
    """Enrich-атрибуты одного адресного объекта; ключ — (osm_type, osm_id)."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_address_enrich"
        unique_together: list[tuple[str, str]] = [("osm_type", "osm_id")]

    id: int | None = DbField(default=None, db_pk=True)
    osm_type: str = DbField(max_length=16)
    osm_id: int = DbField(db_type="BIGINT")
    gar_guid: str = DbField(default="", db_type="TEXT")
    canonical_name: str = DbField(default="", db_type="TEXT")
    cadastral_number: str = DbField(default="", db_type="TEXT")
    updated_at: datetime = DbField()

    @classmethod
    async def by_object(cls, *, osm_type: str, osm_id: int) -> Self | None:
        """Строка обогащения по стабильному ключу объекта."""
        return await cls.objects.filter(osm_type=osm_type, osm_id=osm_id).first()

    @classmethod
    async def upsert_by_object(cls, item: Self) -> Self:
        """Merge по (osm_type, osm_id): обновляет только непустые атрибуты."""
        existing = await cls.by_object(osm_type=item.osm_type, osm_id=item.osm_id)
        if existing is None:
            item.updated_at = datetime.now(UTC)
            return await cls.objects.create(instance=item)
        if item.gar_guid:
            existing.gar_guid = item.gar_guid
        if item.canonical_name:
            existing.canonical_name = item.canonical_name
        if item.cadastral_number:
            existing.cadastral_number = item.cadastral_number
        existing.updated_at = datetime.now(UTC)
        _ = await existing.save()
        return existing

    @classmethod
    async def delete_by_object(cls, *, osm_type: str, osm_id: int) -> int:
        """Удаление enrich-строки объекта (откат к source-truth)."""
        return await cls.objects.filter(osm_type=osm_type, osm_id=osm_id).delete()

    @classmethod
    async def delete_by_guids(cls, guids: list[str]) -> int:
        """Снятие enrich-строк по GAR GUID'ам (объекты, выведенные из ФИАС)."""
        if not guids:
            return 0
        return await cls.objects.filter(gar_guid__in=guids).delete()

    @classmethod
    async def bulk_upsert(
        cls, rows: list[tuple[str, int, str, str]], *, chunk_size: int = 5000
    ) -> int:
        """Пакетный upsert (osm_type, osm_id, gar_guid, canonical_name).

        Импортёр ГАР раскладывает сотни тысяч матчей за тик — покадровый
        ``upsert_by_object`` дал бы SELECT+INSERT на строку; multirow
        VALUES-INSERT сливает чанк одним запросом.
        """
        if not rows:
            return 0
        written = 0
        cols = 5
        for offset in range(0, len(rows), chunk_size):
            chunk = rows[offset : offset + chunk_size]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            now = datetime.now(UTC)
            for row in chunk:
                params.extend([row[0], row[1], row[2], row[3], now])
            _ = await execute_raw(
                f"""
                INSERT INTO geo_address_enrich
                    (osm_type, osm_id, gar_guid, canonical_name, updated_at)
                VALUES {values}
                ON CONFLICT (osm_type, osm_id) DO UPDATE
                SET gar_guid = CASE WHEN EXCLUDED.gar_guid <> ''
                                    THEN EXCLUDED.gar_guid ELSE geo_address_enrich.gar_guid END,
                    canonical_name = CASE WHEN EXCLUDED.canonical_name <> ''
                                          THEN EXCLUDED.canonical_name
                                          ELSE geo_address_enrich.canonical_name END,
                    updated_at = EXCLUDED.updated_at
                """,
                params,
                using="geo",
            )
            written += len(chunk)
        return written

    @classmethod
    async def bulk_set_cadastral(
        cls, rows: list[tuple[str, int, str]], *, chunk_size: int = 5000
    ) -> int:
        """Пакетный upsert ``cadastral_number`` по (osm_type, osm_id, kn)."""
        if not rows:
            return 0
        written = 0
        cols = 4
        for offset in range(0, len(rows), chunk_size):
            chunk = rows[offset : offset + chunk_size]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            now = datetime.now(UTC)
            for row in chunk:
                params.extend([row[0], row[1], row[2], now])
            _ = await execute_raw(
                f"""
                INSERT INTO geo_address_enrich
                    (osm_type, osm_id, cadastral_number, updated_at)
                VALUES {values}
                ON CONFLICT (osm_type, osm_id) DO UPDATE
                SET cadastral_number = CASE WHEN EXCLUDED.cadastral_number <> ''
                                            THEN EXCLUDED.cadastral_number
                                            ELSE geo_address_enrich.cadastral_number END,
                    updated_at = EXCLUDED.updated_at
                """,
                params,
                using="geo",
            )
            written += len(chunk)
        return written
