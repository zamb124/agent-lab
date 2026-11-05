"""Светофор из OSM-ноды ``highway=traffic_signals``.

Таблица ``geo_traffic_signals`` (``__global_model__``). Вершина графа с
сигналом: роутинг добавляет ``signal_delay_s[mode]`` секунд за транзит
через узел — среднее время ожидания зелёного, а не запрет проезда.
``geom geometry(Point,4326)`` — GENERATED ALWAYS из ``lat``/``lng`` в
миграции, в модели не объявлен.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoTrafficSignal(PlatformModel):
    """Строка светофора поколения импорта."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_traffic_signals"

    id: int = DbField(db_pk=True)
    generation: int = DbField(default=0)
    region: str = DbField(default="", max_length=64)
    osm_node_id: int = DbField(db_type="BIGINT")
    lat: float = DbField()
    lng: float = DbField()
    created_at: datetime = DbField()
