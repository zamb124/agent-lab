"""Слои карты: реестр, счётчики и GeoJSON-фичи по рамке.

Фичи — ``ST_AsGeoJSON(geom)`` по каноническим таблицам из ``GEO_LAYERS``:
идентификаторы таблиц и колонок берутся только из реестра (белый список
кода), параметризуются лишь значения bbox и поколение. Пространственный
фильтр — ``geom && ST_MakeEnvelope``, предел строк — ``max_features``
слоя. Spatial-SQL живёт здесь по конвенции домена (см. GeoAddressService):
предикаты Oxyde PostGIS-выражений не покрывают.
"""

from __future__ import annotations

from oxyde import execute_raw

from apps.geo.layers import GEO_LAYER_INDEX, GEO_LAYERS, GeoLayer
from apps.geo.models.api import (
    GeoFeature,
    GeoFeatureCollectionResponse,
    GeoLayerInfo,
    GeoLayerListResponse,
)
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.services.geo_coverage_service import GeoCoverageError
from core.models.base import FlexibleBaseModel, StrictBaseModel
from core.types import SqlParameterValue, parse_json_object


class _FeatureRow(FlexibleBaseModel):
    """Строка SELECT слоя: id + GeoJSON; колонки-свойства — в ``model_extra``."""

    fid: str
    geojson: str


class _CountRow(StrictBaseModel):
    """Строка ``SELECT count(*) AS c``."""

    c: int


class GeoLayerService:
    """Наблюдаемость и выборка канонических слоёв карты."""

    async def layers_response(self) -> GeoLayerListResponse:
        """Слои реестра со счётчиками фич активного поколения."""
        generation = await GeoImportState.active_generation()
        layers: list[GeoLayerInfo] = []
        for layer in GEO_LAYERS:
            layers.append(
                GeoLayerInfo(
                    name=layer.name,
                    geometry=layer.geometry,
                    min_zoom=layer.min_zoom,
                    max_features=layer.max_features,
                    color=layer.color,
                    features=await self._count_features(layer, generation),
                )
            )
        return GeoLayerListResponse(layers=layers, generation=generation)

    async def features_response(
        self,
        *,
        south: float,
        west: float,
        north: float,
        east: float,
        zoom: int,
        layer_names: list[str],
    ) -> GeoFeatureCollectionResponse:
        """Фичи запрошенных слоёв в рамке; слои под ``min_zoom`` пусты."""
        if south >= north or west >= east:
            raise GeoCoverageError(
                "geo_bbox_invalid", f"invalid bbox {south},{west},{north},{east}"
            )
        layers = self._resolve_layers(layer_names)
        generation = await GeoImportState.active_generation()
        features: list[GeoFeature] = []
        truncated = False
        for layer in layers:
            if zoom < layer.min_zoom:
                continue
            layer_features = await self._features_in_bbox(
                layer,
                generation=generation,
                south=south,
                west=west,
                north=north,
                east=east,
            )
            truncated = truncated or len(layer_features) >= layer.max_features
            features.extend(layer_features)
        return GeoFeatureCollectionResponse(features=features, truncated=truncated)

    @staticmethod
    def _resolve_layers(layer_names: list[str]) -> list[GeoLayer]:
        if not layer_names:
            return list(GEO_LAYERS)
        resolved: list[GeoLayer] = []
        for name in layer_names:
            layer = GEO_LAYER_INDEX.get(name)
            if layer is None:
                raise GeoCoverageError(
                    "geo_layer_unknown", f"unknown geo layer {name!r}"
                )
            resolved.append(layer)
        return resolved

    @staticmethod
    async def _count_features(layer: GeoLayer, generation: int) -> int:
        if layer.generation_filtered:
            rows = await execute_raw(
                f"SELECT count(*) AS c FROM {layer.table} WHERE generation = $1",
                [generation],
                using="geo",
            )
        else:
            rows = await execute_raw(
                f"SELECT count(*) AS c FROM {layer.table}",
                [],
                using="geo",
            )
        return _CountRow.model_validate(rows[0]).c

    @staticmethod
    async def _features_in_bbox(
        layer: GeoLayer,
        *,
        generation: int,
        south: float,
        west: float,
        north: float,
        east: float,
    ) -> list[GeoFeature]:
        id_expr = "name" if layer.name == "regions" else "id::text"
        prop_cols = ", ".join(layer.properties)
        where = "geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)"
        params: list[SqlParameterValue] = [west, south, east, north]
        if layer.generation_filtered:
            where = f"generation = ${len(params) + 1} AND {where}"
            params.append(generation)
        params.append(layer.max_features)
        rows = await execute_raw(
            f"SELECT {id_expr} AS fid, ST_AsGeoJSON(geom) AS geojson, {prop_cols}"
            + f" FROM {layer.table} WHERE {where} LIMIT ${len(params)}",
            params,
            using="geo",
        )
        features: list[GeoFeature] = []
        for row in rows:
            feature_row = _FeatureRow.model_validate(row)
            features.append(
                GeoFeature(
                    layer=layer.name,
                    id=feature_row.fid,
                    geometry=parse_json_object(
                        feature_row.geojson, "layer feature geometry"
                    ),
                    properties=feature_row.json_extra(),
                )
            )
        return features
