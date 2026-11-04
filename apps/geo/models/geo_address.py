"""Адресный объект OSM: узел или центроид way с ``addr:housenumber``.

Таблица ``geo_addresses`` — платформенный справочник (``__global_model__``).
Колонка ``geom geometry(Point,4326)`` — GENERATED ALWAYS из ``(lng, lat)``
в миграции, в модели не объявлена: читают её только SQL-запросы
``GeoAddressService``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


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
    generation: int = DbField(default=0)
    created_at: datetime = DbField()
