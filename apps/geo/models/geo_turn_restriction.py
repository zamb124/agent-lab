"""Запрет поворота из OSM-отношения ``type=restriction``.

Таблица ``geo_turn_restrictions`` (``__global_model__``). Строки хранят
сырые ссылки участников (from/to — way, via — node или way); резолв в
id ребёр делает сам запрос роутинга джойном к ``geo_road_edges`` того же
поколения — так одна рестрикция покрывает все рёбра-сегменты way.
``via_lat``/``via_lng`` проставляет импортёр после заливки вершин, а
``geom geometry(Point,4326)`` — GENERATED ALWAYS из них в миграции, в
модели не объявлен. Рестрикции с ``via``-way (магистрали) резолва в
узел не имеют — хранятся для слоя и будущего резолва.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoTurnRestriction(PlatformModel):
    """Строка запрета поворота поколения импорта."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_turn_restrictions"

    id: int = DbField(db_pk=True)
    generation: int = DbField(default=0)
    region: str = DbField(default="", max_length=64)
    osm_relation_id: int = DbField(db_type="BIGINT")
    restriction: str = DbField(max_length=64)
    from_way: int = DbField(db_type="BIGINT")
    to_way: int = DbField(db_type="BIGINT")
    via_node: int | None = DbField(default=None)
    via_way: int | None = DbField(default=None)
    via_lat: float | None = DbField(default=None)
    via_lng: float | None = DbField(default=None)
    created_at: datetime = DbField()
