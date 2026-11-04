"""Ребро дорожного графа между соседними нодами OSM-way.

Таблица ``geo_road_edges`` (``__global_model__``). Имена ``source``/``target``/
``cost``/``reverse_cost`` — контракт pgRouting: ``edges_sql`` читает их
напрямую. Стоимость хранится в секундах по профилям ``car``/``foot``/
``bike``/``scooter``; ``-1`` — проезд в направлении запрещён. Колонка
``geom`` — GENERATED ALWAYS ``ST_MakeLine`` из координат концов в миграции.
"""

from __future__ import annotations

from typing import ClassVar

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoRoadEdge(PlatformModel):
    """Сегмент дороги поколения импорта."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_road_edges"

    id: int = DbField(db_pk=True)
    source: int = DbField(db_type="BIGINT")
    target: int = DbField(db_type="BIGINT")
    src_lat: float = DbField()
    src_lng: float = DbField()
    dst_lat: float = DbField()
    dst_lng: float = DbField()
    length_m: float = DbField()
    car_cost: float = DbField()
    car_reverse_cost: float = DbField()
    foot_cost: float = DbField()
    foot_reverse_cost: float = DbField()
    bike_cost: float = DbField(default=-1.0)
    bike_reverse_cost: float = DbField(default=-1.0)
    scooter_cost: float = DbField(default=-1.0)
    scooter_reverse_cost: float = DbField(default=-1.0)
    oneway: int = DbField(default=0)
    highway: str = DbField(default="", db_type="TEXT")
    name: str = DbField(default="", db_type="TEXT")
    osm_way_id: int = DbField(db_type="BIGINT")
    generation: int = DbField(default=0)
