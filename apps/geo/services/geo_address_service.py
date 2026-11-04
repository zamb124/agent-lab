"""Адресные запросы к PostGIS-справочнику.

Общий фильтр всех запросов — поколение ``geo_import_state.current_generation``:
данные видны только после атомарного свопа импортёра. Пространственные
предикаты Oxyde не выражает — сырые SQL через ``execute_raw`` на алиасе
``geo``; ``geom``-колонка живёт в DDL миграции.
"""

from __future__ import annotations

from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.api import GeoAddressHit, GeoAddressListResponse
from apps.geo.models.geo_import_state import GeoImportState

_ADDRESS_SELECT = """
    SELECT id, osm_type, osm_id, display_name, city, street, housenumber,
           postcode, lat, lng
    FROM geo_addresses
"""


def _hits(rows: list[dict[str, object]]) -> list[GeoAddressHit]:
    """Строки справочника → доменные модели; колонки SELECT = полям модели."""
    return [GeoAddressHit.model_validate(row) for row in rows]


class GeoAddressService:
    """Точечные адресные запросы: в зоне, подсказки, ближайшие."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def addresses_in_zone_by_name_asc(
        self,
        *,
        zone_geojson: str,
        query: str | None,
        limit: int,
        offset: int,
    ) -> GeoAddressListResponse:
        """Адреса внутри полигона.

        ``ST_Covers`` — адрес ровно на границе зоны считается внутри
        (бизнес-семантика «мы туда возим»). Возвращает страницу и точный
        total — директору нужен реальный счётчик.
        """
        generation = await GeoImportState.active_generation()
        where = """
            generation = $1
            AND ST_Covers(ST_GeomFromGeoJSON($2), geom)
            AND ($3::text IS NULL OR display_name % $3 OR display_name ILIKE $3 || '%')
        """
        rows = await execute_raw(
            _ADDRESS_SELECT
            + f"WHERE {where} ORDER BY display_name LIMIT $4 OFFSET $5",
            [generation, zone_geojson, query, limit, offset],
            using="geo",
        )
        count_rows = await execute_raw(
            f"SELECT COUNT(*) AS total FROM geo_addresses WHERE {where}",
            [generation, zone_geojson, query],
            using="geo",
        )
        total: int = count_rows[0]["total"] if count_rows else 0
        return GeoAddressListResponse(items=_hits(rows), total=total)

    async def suggest_by_score_desc(
        self,
        *,
        query: str,
        zone_geojson: str | None,
        lat: float | None,
        lng: float | None,
        limit: int,
    ) -> list[GeoAddressHit]:
        """Автокомплит: префикс → триграм-сходство → близость к точке."""
        generation = await GeoImportState.active_generation()
        rows = await execute_raw(
            _ADDRESS_SELECT
            + """
            WHERE generation = $1
              AND ($2::text IS NULL OR ST_Covers(ST_GeomFromGeoJSON($2), geom))
              AND (display_name ILIKE $3 || '%' OR display_name % $3)
            ORDER BY (display_name ILIKE $3 || '%') DESC,
                     similarity(display_name, $3) DESC,
                     CASE WHEN $4::float IS NULL
                          THEN 0::float
                          ELSE geom <-> ST_SetSRID(ST_MakePoint($5::float, $4::float), 4326)
                     END,
                     display_name
            LIMIT $6
            """,
            [generation, zone_geojson, query, lat, lng, limit],
            using="geo",
        )
        return _hits(rows)

    async def nearest_by_distance(
        self, *, lat: float, lng: float, limit: int
    ) -> list[GeoAddressHit]:
        """Ближайшие адреса к точке (GiST KNN по ``geom <->``)."""
        generation = await GeoImportState.active_generation()
        rows = await execute_raw(
            _ADDRESS_SELECT
            + """
            WHERE generation = $1
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint($2, $3), 4326)
            LIMIT $4
            """,
            [generation, lng, lat, limit],
            using="geo",
        )
        return _hits(rows)
