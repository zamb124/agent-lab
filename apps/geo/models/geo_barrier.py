"""Барьер на пути из OSM-ноды ``barrier=*``.

Таблица ``geo_barriers`` (``__global_model__``). Импортёр хранит сырой
тип барьера и выводит флаги ``block_<mode>`` из типа и access-тегов —
роутинг читает именно флаги, семантика OSM остаётся на границе импорта.
``geom geometry(Point,4326)`` — GENERATED ALWAYS из ``lat``/``lng`` в
миграции, в модели не объявлен.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoBarrier(PlatformModel):
    """Строка барьера поколения импорта."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_barriers"

    id: int = DbField(db_pk=True)
    generation: int = DbField(default=0)
    region: str = DbField(default="", max_length=64)
    osm_node_id: int = DbField(db_type="BIGINT")
    barrier: str = DbField(max_length=64)
    block_car: bool = DbField(default=False)
    block_foot: bool = DbField(default=False)
    block_bike: bool = DbField(default=False)
    block_scooter: bool = DbField(default=False)
    lat: float = DbField()
    lng: float = DbField()
    created_at: datetime = DbField()
