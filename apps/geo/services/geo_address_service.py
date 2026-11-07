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
from core.types import JsonObject, SqlParameterValue

_ADDRESS_SELECT = """
    SELECT id, osm_type, osm_id, display_name, city, street, housenumber,
           postcode, lat, lng
    FROM geo_addresses
"""


def _hits(rows: list[JsonObject]) -> list[GeoAddressHit]:
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

        Nullable-параметры не биндятся — баг oxyde-core prepared
        statement (NULL↔non-NULL сдвигает биндинги); фильтр по запросу
        собирается отдельной SQL-веткой.
        """
        generation = await GeoImportState.active_generation()
        clauses = [
            "generation IN (0, $1)",
            "ST_Covers(ST_GeomFromGeoJSON($2), geom)",
        ]
        params: list[SqlParameterValue] = [generation, zone_geojson]
        if query is not None:
            idx = len(params) + 1
            clauses.append(f"(display_name % ${idx} OR display_name ILIKE ${idx} || '%')")
            params.append(query)
        where = " AND ".join(clauses)
        page_idx = len(params) + 1
        rows = await execute_raw(
            _ADDRESS_SELECT
            + f"WHERE {where} ORDER BY display_name LIMIT ${page_idx} OFFSET ${page_idx + 1}",
            [*params, limit, offset],
            using="geo",
        )
        count_rows = await execute_raw(
            f"SELECT COUNT(*) AS total FROM geo_addresses WHERE {where}",
            params,
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
        """Автокомплит: префикс → триграм-сходство → близость к точке.

        Nullable-параметры не биндятся — баг oxyde-core prepared
        statement (NULL↔non-NULL сдвигает биндинги → «invalid GeoJSON
        representation» на проде); опциональные фильтры — отдельные
        SQL-ветки.
        """
        generation = await GeoImportState.active_generation()
        clauses = ["generation IN (0, $1)"]
        params: list[SqlParameterValue] = [generation]
        if zone_geojson is not None:
            idx = len(params) + 1
            clauses.append(f"ST_Covers(ST_GeomFromGeoJSON(${idx}), geom)")
            params.append(zone_geojson)
        q_idx = len(params) + 1
        clauses.append(f"(display_name ILIKE ${q_idx} || '%' OR display_name % ${q_idx})")
        params.append(query)
        order = (
            f"(display_name ILIKE ${q_idx} || '%') DESC, similarity(display_name, ${q_idx}) DESC"
        )
        if lat is not None and lng is not None:
            lat_idx = len(params) + 1
            order += f", geom <-> ST_SetSRID(ST_MakePoint(${lat_idx + 1}, ${lat_idx}), 4326)"
            params.extend([lat, lng])
        order += ", display_name"
        limit_idx = len(params) + 1
        params.append(limit)
        rows = await execute_raw(
            _ADDRESS_SELECT + f"WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT ${limit_idx}",
            params,
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
            WHERE generation IN (0, $1)
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint($2, $3), 4326)
            LIMIT $4
            """,
            [generation, lng, lat, limit],
            using="geo",
        )
        return _hits(rows)
