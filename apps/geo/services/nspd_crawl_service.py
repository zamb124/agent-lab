"""Краулер НСПД/ЕГРН: контуры зданий и кадастровые номера адресов.

Публичный API ``nspd.gov.ru`` (контракт как у ``pynspd``):

- ``POST /api/geoportal/v1/intersects?typeIntersect=fullObject`` — объекты
  категории внутри полигона; слишком большой контур — ``code:400104``.
- ``GET /api/geoportal/v2/search/geoportal?query=&layersId=`` — поиск по
  тексту/кадастровому номеру; ответ ``{data: FeatureCollection, meta}``.
- Без ``Referer: https://nspd.gov.ru/map?thematic=PKK`` — 403; при
  агрессии — бан, поэтому клиент держит ``nspd_rps`` и ретраит 403/429/5xx
  с backoff.

Краул: сетка ячеек ``nspd_cell_deg`` по bbox каждого активного
``GeoRegion``; курсор ``geo_source_cursors(source='nspd')`` — индекс
следующей ячейки, тик делает ``nspd_tick_batch`` ячеек и сохраняет
позицию (resume). Полный проход → курсор DONE; следующий тик начинает
новый проход (данные идемпотентно перевставляются).

Здания → ``geo_buildings`` (upsert по cadastral_number); адресные точки
внутри контуров → ``cadastral_number`` в ``geo_address_enrich`` и живых
строках. ``gar_unresolved`` (дома ГАР без адреса OSM) резолвится поиском
по каноническому имени: найденное здание даёт точку — материализуется
``geo_addresses`` ``source='gar', osm_type='gar', generation=0``; промах
→ defer, payload не теряется.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, TypeAdapter

from apps.geo.config import GeoSettings
from apps.geo.db.import_lock import geo_import_lock
from apps.geo.models.geo_address import GeoAddress
from apps.geo.models.geo_address_enrich import GeoAddressEnrich
from apps.geo.models.geo_building import GeoBuilding
from apps.geo.models.geo_enrich_item import GeoEnrichItem
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_region import GeoRegion
from apps.geo.models.geo_source import GeoSource
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.models.geo_stats import GeoStats
from apps.geo.services.gar_import_service import UNRESOLVED_KIND
from apps.geo.services.geo_enrich_service import (
    GeoEnrichDeferred,
    GeoEnrichService,
)
from core.http import get_httpx_client
from core.http.client import SmartProxyClient
from core.logging import get_logger
from core.types import JsonObject, JsonValue

_SOURCE = "nspd"
_GAR_SOURCE = "gar"
_NSPD_LOCK_KEY = "geo.nspd_crawl"

_logger = get_logger(__name__)

_JSON_OBJECT: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)


class _NspdFeature(BaseModel):
    """Feature из FeatureCollection НСПД: ``properties.options`` — атрибуты."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    properties: JsonObject = {}
    geometry: JsonObject | None = None


class _IntersectsResponse(BaseModel):
    """Ответ ``/api/geoportal/v1/intersects`` — FeatureCollection напрямую."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    features: list[_NspdFeature] = []


class _SearchData(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    features: list[_NspdFeature] = []


class _SearchResponse(BaseModel):
    """Ответ ``/api/geoportal/v2/search/geoportal``."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    data: _SearchData


class NspdCrawlResult(BaseModel):
    """Итог тика краула: ``skipped`` — причина пропуска, иначе по регионам."""

    skipped: str = ""
    regions: dict[str, JsonObject] = {}


class NspdClient:
    """HTTP-клиент НСПД: Referer, минимальный интервал между запросами, retry."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings
        self._rate_lock: asyncio.Lock = asyncio.Lock()
        self._last_request: float = 0.0

    async def _throttle(self) -> None:
        """Минимум ``1/nspd_rps`` секунды между запросами к НСПД."""
        async with self._rate_lock:
            now = time.monotonic()
            pause = self._last_request + (1.0 / self._settings.nspd_rps) - now
            if pause > 0:
                await asyncio.sleep(pause)
            self._last_request = time.monotonic()

    async def _request(
        self,
        client: SmartProxyClient,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        body: JsonObject | None = None,
    ) -> JsonObject:
        """Запрос с retry при 403/429/5xx и транспортных сбоях (backoff)."""
        url = f"{self._settings.nspd_base_url}{path}"
        headers = {"Referer": self._settings.nspd_referer}
        last_error = ""
        for attempt in range(1, self._settings.nspd_max_retries + 1):
            await self._throttle()
            try:
                if method == "post":
                    response = await client.post(
                        url, params=params, json=body, headers=headers
                    )
                else:
                    response = await client.get(url, params=params, headers=headers)
                if response.status_code == 404:
                    return {}
                if response.status_code in (403, 429) or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                else:
                    _ = response.raise_for_status()
                    return _JSON_OBJECT.validate_json(response.content)
            except Exception as exc:  # транспорт/JSON — тоже retry
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < self._settings.nspd_max_retries:
                await asyncio.sleep(
                    self._settings.nspd_retry_pause_seconds * attempt
                )
        raise RuntimeError(f"nspd request failed after retries: {last_error}")

    async def intersects(
        self,
        client: SmartProxyClient,
        *,
        polygon: JsonObject,
        category_id: int,
    ) -> list[_NspdFeature]:
        """Объекты категории (здания) внутри ячейки."""
        geom = dict(polygon)
        geom["crs"] = {"type": "name", "properties": {"name": "EPSG:4326"}}
        body: JsonObject = {
            "categories": [{"id": category_id}],
            "geom": {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {}, "geometry": geom}
                ],
            },
        }
        payload = await self._request(
            client,
            "post",
            "/api/geoportal/v1/intersects",
            params={"typeIntersect": "fullObject"},
            body=body,
        )
        if not payload:
            return []
        return _IntersectsResponse.model_validate(payload).features

    async def search_buildings(
        self, client: SmartProxyClient, *, query: str
    ) -> list[_NspdFeature]:
        """Поиск объектов слоя «Здания» по тексту/кадастровому номеру."""
        payload = await self._request(
            client,
            "get",
            "/api/geoportal/v2/search/geoportal",
            params={
                "query": query,
                "layersId": str(self._settings.nspd_building_layer_id),
            },
        )
        if not payload:
            return []
        return _SearchResponse.model_validate(payload).data.features


def _options(feature: _NspdFeature) -> JsonObject:
    """``properties.options`` — атрибуты объекта НСПД."""
    options = feature.properties.get("options")
    return options if isinstance(options, dict) else {}


def _cad_num(feature: _NspdFeature) -> str:
    return str(_options(feature).get("cad_num", ""))


def _address(feature: _NspdFeature) -> str:
    return str(_options(feature).get("address", ""))


def _centroid(feature: _NspdFeature) -> tuple[float, float] | None:
    """Центроид внешнего кольца полигона (lng, lat); ``None`` — геометрии нет."""
    geometry = feature.geometry
    if not geometry:
        return None
    gtype = str(geometry.get("type", ""))
    coords = geometry.get("coordinates")
    ring: JsonValue | None = None
    if gtype == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0]
    elif (
        gtype == "MultiPolygon"
        and isinstance(coords, list)
        and coords
        and isinstance(coords[0], list)
        and coords[0]
    ):
        ring = coords[0][0]
    points: list[tuple[float, float]] = []
    if isinstance(ring, list):
        points = [
            (float(str(p[0])), float(str(p[1])))
            for p in ring
            if isinstance(p, list) and len(p) >= 2
        ]
    if not points:
        return None
    lng = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return lat, lng


class NspdCrawlService:
    """Тик краула НСПД: ячейки сетки → здания → кадастровые линки."""

    def __init__(
        self, settings: GeoSettings, geo_enrich_service: GeoEnrichService
    ) -> None:
        self._settings: GeoSettings = settings
        geo_enrich_service.register_handler(
            kind=UNRESOLVED_KIND, handler=self._resolve_gar_unresolved
        )

    async def run_crawl(self) -> NspdCrawlResult:
        """Тик: пачка ячеек сетки региона → upsert зданий + кадастр-линк."""
        if not self._settings.nspd_sync_enabled:
            return NspdCrawlResult(skipped="nspd_sync_disabled")
        source = await GeoSource.by_name(_SOURCE)
        if source is not None and not source.enabled:
            return NspdCrawlResult(skipped="source_disabled")
        regions = await GeoRegion.list_enabled_by_name_asc()
        if not regions:
            return NspdCrawlResult(skipped="no_regions")
        async with geo_import_lock(
            self._settings.database.geo_url, key=_NSPD_LOCK_KEY
        ) as acquired:
            if not acquired:
                return NspdCrawlResult(skipped="locked")
            client = NspdClient(self._settings)
            async with get_httpx_client(
                timeout=self._settings.nspd_http_timeout_seconds
            ) as http:
                results: dict[str, JsonObject] = {}
                generation = await GeoImportState.active_generation()
                for region in regions:
                    results[region.name] = await self._crawl_region(
                        client, http, region=region, generation=generation
                    )
                return NspdCrawlResult(regions=results)

    async def _crawl_region(
        self,
        client: NspdClient,
        http: SmartProxyClient,
        *,
        region: GeoRegion,
        generation: int,
    ) -> JsonObject:
        """Ячейки сетки региона: intersects → здания → cadastral-линк."""
        cells = self._cells(region)
        if not cells:
            return {"status": "empty"}
        cursor = await GeoSourceCursor.by_source_region(_SOURCE, region.name)
        done_index = (
            int(cursor.cursor)
            if cursor is not None and cursor.cursor.isdigit()
            else 0
        )
        if (
            cursor is not None
            and cursor.status == GeoCursorStatus.DONE
            and done_index >= len(cells)
        ):
            done_index = 0
        if done_index >= len(cells):
            return {"status": "current", "cells": len(cells)}
        batch = cells[done_index : done_index + self._settings.nspd_tick_batch]
        buildings_seen = 0
        try:
            for index, polygon in batch:
                features = await client.intersects(
                    http,
                    polygon=polygon,
                    category_id=self._settings.nspd_building_layer_id,
                )
                buildings_seen += await self._upsert_buildings(
                    region.name, features
                )
                next_index = index + 1
                status = (
                    GeoCursorStatus.DONE
                    if next_index >= len(cells)
                    else GeoCursorStatus.RUNNING
                )
                _ = await GeoSourceCursor.upsert_progress(
                    source=_SOURCE,
                    region=region.name,
                    cursor=str(next_index),
                    rows_done=buildings_seen,
                    status=status,
                )
        except Exception as exc:
            await GeoSourceCursor.mark_failed(
                source=_SOURCE,
                region=region.name,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        links = await GeoAddress.list_cadastral_links_asc(
            region=region.name, generation=generation
        )
        _ = await GeoAddressEnrich.bulk_set_cadastral(links)
        _ = await GeoAddress.bulk_set_cadastral(links, generation=generation)
        await GeoStats.set_rows(
            generation=0,
            source=_SOURCE,
            region=region.name,
            entity="building",
            rows=await GeoBuilding.count_for_region(region.name),
        )
        return {
            "status": "done" if batch[-1][0] + 1 >= len(cells) else "running",
            "cells": len(batch),
            "cells_total": len(cells),
            "buildings": buildings_seen,
            "cadastral_links": len(links),
        }

    def _cells(self, region: GeoRegion) -> list[tuple[int, JsonObject]]:
        """Сетка ячеек ``(index, polygon-geojson)`` по bbox региона."""
        cell = self._settings.nspd_cell_deg
        lat_min, lng_min = region.bbox_south, region.bbox_west
        lat_max, lng_max = region.bbox_north, region.bbox_east
        rows = max(1, round((lat_max - lat_min) / cell))
        cols = max(1, round((lng_max - lng_min) / cell))
        cells: list[tuple[int, JsonObject]] = []
        index = 0
        for r in range(rows):
            for c in range(cols):
                south = lat_min + r * (lat_max - lat_min) / rows
                north = lat_min + (r + 1) * (lat_max - lat_min) / rows
                west = lng_min + c * (lng_max - lng_min) / cols
                east = lng_min + (c + 1) * (lng_max - lng_min) / cols
                cells.append(
                    (
                        index,
                        {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [west, south],
                                    [east, south],
                                    [east, north],
                                    [west, north],
                                    [west, south],
                                ]
                            ],
                        },
                    )
                )
                index += 1
        return cells

    async def _upsert_buildings(
        self, region: str, features: list[_NspdFeature]
    ) -> int:
        """``geo_buildings`` upsert по cadastral_number из intersects-фич."""
        written = 0
        for feature in features:
            cad_num = _cad_num(feature)
            centroid = _centroid(feature)
            if not cad_num or centroid is None:
                continue
            lat, lng = centroid
            now = datetime.now(UTC)
            _ = await GeoBuilding.upsert_by_cadastral_number(
                GeoBuilding(
                    cadastral_number=cad_num,
                    address=_address(feature),
                    lat=lat,
                    lng=lng,
                    geojson=json.dumps(feature.geometry, ensure_ascii=False),
                    region=region,
                    source=_SOURCE,
                    created_at=now,
                    updated_at=now,
                )
            )
            written += 1
        return written

    async def _resolve_gar_unresolved(self, item: GeoEnrichItem) -> None:
        """Резолвер ``gar_unresolved``: дом ГАР без адреса OSM → точка НСПД.

        Каноническое имя → search по слою «Здания» → центроид контура →
        gen-0 ``geo_addresses`` ``osm_type='gar'`` + enrich (gar_guid +
        cadastral_number). Промах — defer: payload живёт до удачного резолва.
        """
        if not self._settings.nspd_sync_enabled:
            raise GeoEnrichDeferred(self._settings.nspd_unresolved_defer_seconds)
        canonical = str(item.payload.get("canonical_name", ""))
        street = str(item.payload.get("street", ""))
        housenum = str(item.payload.get("housenum", ""))
        region = str(item.payload.get("region", ""))
        gar_objectid = str(item.payload.get("gar_objectid", ""))
        gar_guid = str(item.payload.get("gar_guid", ""))
        if not canonical or not gar_objectid.isdigit():
            raise GeoEnrichDeferred(self._settings.nspd_unresolved_defer_seconds)
        client = NspdClient(self._settings)
        async with get_httpx_client(
            timeout=self._settings.nspd_http_timeout_seconds
        ) as http:
            features = await client.search_buildings(http, query=canonical)
        hit = self._pick_building(features, housenum=housenum)
        if hit is None:
            raise GeoEnrichDeferred(self._settings.nspd_unresolved_defer_seconds)
        centroid = _centroid(hit)
        cad_num = _cad_num(hit)
        if centroid is None:
            raise GeoEnrichDeferred(self._settings.nspd_unresolved_defer_seconds)
        lat, lng = centroid
        now = datetime.now(UTC)
        if cad_num:
            _ = await GeoBuilding.upsert_by_cadastral_number(
                GeoBuilding(
                    cadastral_number=cad_num,
                    address=_address(hit),
                    lat=lat,
                    lng=lng,
                    geojson=json.dumps(hit.geometry, ensure_ascii=False),
                    region=region,
                    source=_SOURCE,
                    created_at=now,
                    updated_at=now,
                )
            )
        osm_id = int(gar_objectid)
        _ = await self._upsert_gar_address(
            osm_id=osm_id,
            display_name=canonical,
            street=street,
            housenum=housenum,
            lat=lat,
            lng=lng,
            region=region,
            gar_guid=gar_guid,
            cad_num=cad_num,
        )
        _ = await GeoAddressEnrich.upsert_by_object(
            GeoAddressEnrich(
                osm_type=_GAR_SOURCE,
                osm_id=osm_id,
                gar_guid=gar_guid,
                canonical_name=canonical,
                cadastral_number=cad_num,
                updated_at=now,
            )
        )

    @staticmethod
    def _pick_building(
        features: list[_NspdFeature], *, housenum: str
    ) -> _NspdFeature | None:
        """Здание, чей адрес подтверждает номер дома; ``None`` — не нашли."""
        for feature in features:
            address = _address(feature)
            if _cad_num(feature) and (
                not housenum
                or f" {housenum}" in address
                or address.endswith(housenum)
                or f", {housenum}" in address
            ):
                return feature
        return features[0] if features and not housenum else None

    @staticmethod
    async def _upsert_gar_address(
        *,
        osm_id: int,
        display_name: str,
        street: str,
        housenum: str,
        lat: float,
        lng: float,
        region: str,
        gar_guid: str,
        cad_num: str,
    ) -> None:
        """Gen-0 адрес ``source='gar'``: точка резолва из контура НСПД."""
        from oxyde import execute_raw

        _ = await execute_raw(
            """
            INSERT INTO geo_addresses
                (osm_type, osm_id, display_name, city, street, housenumber,
                 postcode, lat, lng, region, generation, source, gar_guid,
                 canonical_name, cadastral_number, created_at)
            VALUES ('gar', $1, $2, '', $3, $4,
                    '', $5, $6, $7, 0, 'gar', $8, $2, $9, $10)
            ON CONFLICT (osm_type, osm_id, generation) DO UPDATE
            SET display_name = EXCLUDED.display_name,
                street = EXCLUDED.street,
                housenumber = EXCLUDED.housenumber,
                lat = EXCLUDED.lat,
                lng = EXCLUDED.lng,
                gar_guid = EXCLUDED.gar_guid,
                canonical_name = EXCLUDED.canonical_name,
                cadastral_number = EXCLUDED.cadastral_number
            """,
            [
                osm_id,
                display_name,
                street,
                housenum,
                lat,
                lng,
                region,
                gar_guid,
                cad_num,
                datetime.now(UTC),
            ],
            using="geo",
        )
