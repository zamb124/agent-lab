"""Адресный объект OSM: узел или центроид way с ``addr:housenumber``.

Таблица ``geo_addresses`` — платформенный справочник (``__global_model__``).
Колонка ``geom geometry(Point,4326)`` — GENERATED ALWAYS из ``(lng, lat)``
в миграции, в модели не объявлена: читают её только SQL-запросы
``GeoAddressService``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import execute_raw

from core.models.platform_model import PlatformModel
from core.types import JsonObject, SqlParameterValue


class GeoAddress(PlatformModel):
    """Строка адресного справочника поколения импорта."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_addresses"

    id: int = DbField(db_pk=True)
    osm_type: str = DbField(max_length=16)
    osm_id: int = DbField(db_type="BIGINT")
    display_name: str = DbField(db_type="TEXT")
    city: str = DbField(default="", db_type="TEXT")
    street: str = DbField(default="", db_type="TEXT")
    housenumber: str = DbField(default="", db_type="TEXT")
    postcode: str = DbField(default="", db_type="TEXT")
    lat: float = DbField()
    lng: float = DbField()
    region: str = DbField(default="", max_length=64)
    generation: int = DbField(default=0)
    source: str = DbField(default="osm", max_length=32)
    gar_guid: str = DbField(default="", max_length=36)
    canonical_name: str = DbField(default="", db_type="TEXT")
    cadastral_number: str = DbField(default="", max_length=32)
    created_at: datetime = DbField()

    @classmethod
    async def list_for_enrich_match(cls, *, region: str, generation: int) -> list[Self]:
        """Кандидаты матча внешних источников: все адреса региона живых поколений."""
        return (
            await cls.objects.filter(region=region, generation__in=[0, generation])
            .all()
        )

    @classmethod
    async def clear_gar_attrs(
        cls, *, guids: list[str], generation: int, chunk_size: int = 5000
    ) -> int:
        """Очистка ``gar_guid``/``canonical_name`` у выведенных из ФИАС объектов."""
        cleared = 0
        for offset in range(0, len(guids), chunk_size):
            chunk = guids[offset : offset + chunk_size]
            placeholders = ",".join(f"${k + 1}" for k in range(len(chunk)))
            result = await execute_raw(
                f"""
                UPDATE geo_addresses
                SET gar_guid = '', canonical_name = ''
                WHERE gar_guid IN ({placeholders})
                  AND generation IN (0, ${len(chunk) + 1})
                RETURNING id
                """,
                [*chunk, generation],
                using="geo",
            )
            cleared += len(result)
        return cleared

    @classmethod
    async def bulk_set_gar_attrs(
        cls,
        rows: list[tuple[str, int, str, str]],
        *,
        generation: int,
        chunk_size: int = 5000,
    ) -> int:
        """Простановка ``gar_guid``/``canonical_name`` на живых строках.

        Запись сразу и в enrich-таблицу, и в живые колонки — как у оверлеев
        админа: эффект виден до следующего импорта, своп поколения значения
        перенакатает из ``geo_address_enrich``. Полей админа касаться нельзя.
        """
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
            for row in chunk:
                params.extend([row[0], row[1], row[2], row[3]])
            params.append(generation)
            _ = await execute_raw(
                f"""
                UPDATE geo_addresses AS a
                SET gar_guid = t.gar_guid, canonical_name = t.canonical_name
                FROM (VALUES {values})
                    AS t(osm_type, osm_id, gar_guid, canonical_name)
                WHERE a.osm_type = t.osm_type AND a.osm_id = t.osm_id
                  AND a.generation IN (0, ${len(params)})
                """,
                params,
                using="geo",
            )
            written += len(chunk)
        return written

    @classmethod
    async def list_cadastral_links_asc(
        cls, *, region: str, generation: int
    ) -> list[tuple[str, int, str]]:
        """Пары (osm_type, osm_id, cadastral_number): адресные точки внутри
        контуров ``geo_buildings`` региона без заполненного кадастра."""
        rows: list[JsonObject] = await execute_raw(
            """
            SELECT a.osm_type, a.osm_id, b.cadastral_number
            FROM geo_addresses AS a
            JOIN geo_buildings AS b
              ON ST_Contains(b.geom, ST_SetSRID(ST_Point(a.lng, a.lat), 4326))
            WHERE a.region = $1 AND a.generation IN (0, $2)
              AND b.region = $1 AND a.cadastral_number = ''
            ORDER BY a.osm_id
            """,
            [region, generation],
            using="geo",
        )
        return [
            (
                str(row["osm_type"]),
                int(str(row["osm_id"])),
                str(row["cadastral_number"]),
            )
            for row in rows
        ]

    @classmethod
    async def bulk_set_cadastral(
        cls,
        rows: list[tuple[str, int, str]],
        *,
        generation: int,
        chunk_size: int = 5000,
    ) -> int:
        """Простановка ``cadastral_number`` на живых строках (osm_type, osm_id, kn)."""
        if not rows:
            return 0
        written = 0
        cols = 3
        for offset in range(0, len(rows), chunk_size):
            chunk = rows[offset : offset + chunk_size]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            for row in chunk:
                params.extend([row[0], row[1], row[2]])
            params.append(generation)
            _ = await execute_raw(
                f"""
                UPDATE geo_addresses AS a
                SET cadastral_number = t.cadastral_number
                FROM (VALUES {values})
                    AS t(osm_type, osm_id, cadastral_number)
                WHERE a.osm_type = t.osm_type AND a.osm_id = t.osm_id
                  AND a.generation IN (0, ${len(params)})
                """,
                params,
                using="geo",
            )
            written += len(chunk)
        return written
