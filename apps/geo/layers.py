"""Канонический реестр слоёв Geo.

Один слой — одна таблица ``geo_*``. Панель слоёв в UI и команды
``geo/layers/list|features`` читают только этот реестр: имена таблиц и
колонки в ``properties`` — белый список, зашитый в коде; снаружи приходят
только имена слоёв и значения bbox, поэтому SQL-состав запроса неизменен.
``min_zoom`` — порог видимости в UI (features-оп для слоя под порогом
отдаёт пустой список), ``max_features`` — жёсткий LIMIT на запрос.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeoLayer:
    """Описание канонического слоя: таблица, тип геометрии, белый список свойств."""

    name: str
    table: str
    geometry: str
    properties: tuple[str, ...]
    min_zoom: int
    max_features: int
    color: str
    generation_filtered: bool = True


GEO_LAYERS: tuple[GeoLayer, ...] = (
    GeoLayer(
        name="regions",
        table="geo_regions",
        geometry="polygon",
        properties=("name", "title", "kind", "enabled"),
        min_zoom=0,
        max_features=200,
        color="#8b5cf6",
        generation_filtered=False,
    ),
    GeoLayer(
        name="roads",
        table="geo_road_edges",
        geometry="line",
        properties=("osm_way_id", "highway", "name", "oneway", "length_m"),
        min_zoom=11,
        max_features=1200,
        color="#475569",
    ),
    GeoLayer(
        name="addresses",
        table="geo_addresses",
        geometry="point",
        properties=(
            "display_name",
            "city",
            "street",
            "housenumber",
            "source",
            "canonical_name",
            "cadastral_number",
        ),
        min_zoom=14,
        max_features=500,
        color="#f59e0b",
    ),
    GeoLayer(
        name="restrictions",
        table="geo_turn_restrictions",
        geometry="point",
        properties=(
            "restriction",
            "osm_relation_id",
            "from_way",
            "to_way",
            "via_node",
        ),
        min_zoom=13,
        max_features=400,
        color="#ef4444",
    ),
    GeoLayer(
        name="barriers",
        table="geo_barriers",
        geometry="point",
        properties=(
            "barrier",
            "osm_node_id",
            "block_car",
            "block_foot",
            "block_bike",
            "block_scooter",
        ),
        min_zoom=13,
        max_features=400,
        color="#a855f7",
    ),
    GeoLayer(
        name="buildings",
        table="geo_buildings",
        geometry="polygon",
        properties=("cadastral_number", "address", "source"),
        min_zoom=14,
        max_features=400,
        color="#64748b",
        generation_filtered=False,
    ),
    GeoLayer(
        name="signals",
        table="geo_traffic_signals",
        geometry="point",
        properties=("osm_node_id",),
        min_zoom=13,
        max_features=800,
        color="#f97316",
    ),
)

GEO_LAYER_INDEX: dict[str, GeoLayer] = {layer.name: layer for layer in GEO_LAYERS}
