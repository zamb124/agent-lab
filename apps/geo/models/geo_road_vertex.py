"""Вершина дорожного графа: OSM-нод, участвующий в way с ``highway``.

Таблица ``geo_road_vertices`` (``__global_model__``). PK суррогатный —
``node_id`` = id ноды OSM; уникальность ``(node_id, generation)`` позволяет
сосуществовать поколениям до свопа. ``source``/``target`` рёбер ссылаются
на ``node_id``. Колонка ``geom`` — GENERATED ALWAYS из ``(lng, lat)``.
"""

from __future__ import annotations

from typing import ClassVar

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoRoadVertex(PlatformModel):
    """Вершина дорожного графа поколения импорта."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_road_vertices"

    id: int = DbField(db_pk=True)
    node_id: int = DbField(db_type="BIGINT")
    lat: float = DbField()
    lng: float = DbField()
    region: str = DbField(default="", max_length=64)
    generation: int = DbField(default=0)
