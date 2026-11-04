"""Дорожный роутинг поверх pgRouting и таблиц ``geo_road_*``.

Контракт графа — миграция ``geo/0001``: рёбра хранят стоимость в секундах
по профилям ``car``/``foot`` (``-1`` — направление запрещено). ``edges_sql``
pgRouting собирается под режим и активное поколение (int литералом в тексте —
placeholders внутри ``edges_sql`` pgr не связывает). Порядок TSP считается
детерминированным NN+2-opt поверх матрицы pgRouting — предсказуемо для тестов.
"""

from __future__ import annotations

import json

from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.api import (
    GeoIsochroneResponse,
    GeoRouteLeg,
    GeoRouteMatrixResponse,
    GeoRouteOrderResponse,
    GeoRouteResponse,
)
from apps.geo.models.geo_import_state import GeoImportState
from core.errors.boundary import PlatformNotFoundError, PlatformUnavailableError


class GeoRoutingError(Exception):
    """Ошибка ввода/лимитов роутинга; ``code`` — platform error_code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _edges_sql(cost_col: str, rcost_col: str, generation: int) -> str:
    """SQL-набор рёбер для pgr_* по профилю и поколению.

    Ребро попадает в набор, если проходимо хотя бы в одном направлении;
    ``-1`` в колонке pgr читает как запрет направления.
    """
    return (
        f"SELECT id, source, target, {cost_col} AS cost, {rcost_col} AS reverse_cost "
        f"FROM geo_road_edges "
        f"WHERE generation = {generation} AND ({cost_col} > 0 OR {rcost_col} > 0)"
    )


def _mode_columns(mode: str) -> tuple[str, str]:
    if mode == "foot":
        return "foot_cost", "foot_reverse_cost"
    return "car_cost", "car_reverse_cost"


class GeoRoutingService:
    """Роутинг: маршрут, матрица, оптимальный порядок, изохрона."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def _snap_vertex(self, lat: float, lng: float, *, generation: int) -> int:
        """Ближайшая вершина графа к точке; лимит притяжки из настроек."""
        rows = await execute_raw(
            """
            SELECT node_id,
                   ST_Distance(
                       geom::geography,
                       ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                   ) AS dist_m
            FROM geo_road_vertices
            WHERE generation = $3
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
            LIMIT 1
            """,
            [lng, lat, generation],
            using="geo",
        )
        if not rows:
            raise PlatformUnavailableError(
                "Road graph is empty — run OSM import",
                error_code="geo_import_unavailable",
            )
        dist_m = float(rows[0]["dist_m"])
        if dist_m > self._settings.snap_max_distance_m:
            raise GeoRoutingError(
                "point_too_far_from_road",
                f"Point is {dist_m:.0f}m from the road graph",
            )
        return int(rows[0]["node_id"])

    async def calculate(
        self,
        *,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float,
        mode: str,
    ) -> GeoRouteResponse:
        """Кратчайший путь: дистанция, длительность, геометрия LineString."""
        generation = await GeoImportState.active_generation()
        start_vid = await self._snap_vertex(from_lat, from_lng, generation=generation)
        end_vid = await self._snap_vertex(to_lat, to_lng, generation=generation)
        cost_col, rcost_col = _mode_columns(mode)
        edges_sql = _edges_sql(cost_col, rcost_col, generation)
        rows = await execute_raw(
            """
            WITH path AS (
                SELECT * FROM pgr_dijkstra($1, $2::bigint, $3::bigint, directed => true)
            )
            SELECT COUNT(*) AS legs,
                   COALESCE(SUM(e.length_m), 0) AS distance_m,
                   COALESCE(SUM(p.cost), 0) AS duration_s,
                   ST_AsGeoJSON(
                       ST_LineMerge(ST_Collect(e.geom ORDER BY p.path_seq))
                   )::text AS geometry
            FROM path p
            LEFT JOIN geo_road_edges e ON e.id = p.edge
            """,
            [edges_sql, start_vid, end_vid],
            using="geo",
        )
        row = rows[0]
        if int(row["legs"]) == 0:
            raise PlatformNotFoundError(
                "No route between points", error_code="route_not_found"
            )
        geometry = row["geometry"]
        return GeoRouteResponse(
            distance_m=float(row["distance_m"]),
            duration_s=float(row["duration_s"]),
            geometry=json.loads(str(geometry)) if geometry else None,
        )

    async def matrix(
        self,
        *,
        sources: list[tuple[float, float]],
        targets: list[tuple[float, float]],
        mode: str,
    ) -> GeoRouteMatrixResponse:
        """N×M матрица длительности и дистанции по дорогам."""
        cells = len(sources) * len(targets)
        if cells > self._settings.matrix_max_cells:
            raise GeoRoutingError(
                "matrix_limit_exceeded",
                f"{cells} cells exceed limit {self._settings.matrix_max_cells}",
            )
        generation = await GeoImportState.active_generation()
        src_vids = [
            await self._snap_vertex(lat, lng, generation=generation)
            for lat, lng in sources
        ]
        dst_vids = [
            await self._snap_vertex(lat, lng, generation=generation)
            for lat, lng in targets
        ]
        durations = await self._cost_matrix(
            src_vids, dst_vids, mode=mode, metric="time", generation=generation
        )
        distances = await self._cost_matrix(
            src_vids, dst_vids, mode=mode, metric="distance", generation=generation
        )
        return GeoRouteMatrixResponse(durations_s=durations, distances_m=distances)

    async def _cost_matrix(
        self,
        src_vids: list[int],
        dst_vids: list[int],
        *,
        mode: str,
        metric: str,
        generation: int,
    ) -> list[list[float | None]]:
        cost_col, rcost_col = _mode_columns(mode)
        if metric == "distance":
            # Метры: та же направленность, что и у времени — one-way учитывается.
            edges_sql = (
                "SELECT id, source, target, length_m AS cost, "
                f"CASE WHEN {rcost_col} > 0 THEN length_m ELSE -1 END AS reverse_cost "
                "FROM geo_road_edges "
                f"WHERE generation = {generation} AND ({cost_col} > 0 OR {rcost_col} > 0)"
            )
        else:
            edges_sql = _edges_sql(cost_col, rcost_col, generation)
        rows = await execute_raw(
            """
            SELECT start_vid, end_vid, agg_cost
            FROM pgr_dijkstraCostMatrix($1, $2::bigint[], $3::bigint[])
            """,
            [edges_sql, src_vids, dst_vids],
            using="geo",
        )
        table: dict[tuple[int, int], float] = {
            (int(r["start_vid"]), int(r["end_vid"])): float(r["agg_cost"])
            for r in rows
        }
        return [[table.get((sv, dv)) for dv in dst_vids] for sv in src_vids]

    async def optimal_order(
        self,
        *,
        start: tuple[float, float],
        points: list[tuple[float, float]],
        mode: str,
        with_legs: bool,
    ) -> GeoRouteOrderResponse:
        """Порядок объезда: NN + 2-opt по матрице pgRouting, детерминированно."""
        if len(points) > self._settings.tsp_max_points:
            raise GeoRoutingError(
                "tsp_limit_exceeded",
                f"{len(points)} points exceed limit {self._settings.tsp_max_points}",
            )
        all_points = [start, *points]
        durations = (
            await self.matrix(sources=all_points, targets=all_points, mode=mode)
        ).durations_s
        n = len(all_points)
        order = _two_opt_order(durations, n)
        legs: list[GeoRouteLeg] = []
        total_distance = 0.0
        total_duration = 0.0
        seq = [0, *order[1:], 0]  # старт -> точки в порядке -> возврат к старту
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            leg = await self.calculate(
                from_lat=all_points[a][0],
                from_lng=all_points[a][1],
                to_lat=all_points[b][0],
                to_lng=all_points[b][1],
                mode=mode,
            )
            total_distance += leg.distance_m
            total_duration += leg.duration_s
            if with_legs:
                legs.append(
                    GeoRouteLeg(
                        from_index=a - 1,
                        to_index=b - 1,
                        distance_m=leg.distance_m,
                        duration_s=leg.duration_s,
                        geometry=leg.geometry,
                    )
                )
        return GeoRouteOrderResponse(
            order=[i - 1 for i in order[1:]],
            total_distance_m=total_distance,
            total_duration_s=total_duration,
            legs=legs,
        )

    async def isochrone(
        self, *, lat: float, lng: float, minutes: float, mode: str
    ) -> GeoIsochroneResponse:
        """Полигон достижимости за ``minutes`` минут от точки."""
        if minutes > self._settings.isochrone_max_minutes:
            raise GeoRoutingError(
                "isochrone_limit_exceeded",
                f"{minutes}min exceed limit {self._settings.isochrone_max_minutes}min",
            )
        generation = await GeoImportState.active_generation()
        start_vid = await self._snap_vertex(lat, lng, generation=generation)
        cost_col, rcost_col = _mode_columns(mode)
        edges_sql = _edges_sql(cost_col, rcost_col, generation)
        rows = await execute_raw(
            """
            WITH reach AS (
                SELECT node, agg_cost
                FROM pgr_drivingDistance($1, $2::bigint, $3)
            )
            SELECT COUNT(*) AS vertices,
                   CASE WHEN COUNT(*) >= 3
                        THEN ST_AsGeoJSON(ST_ConcaveHull(ST_Collect(v.geom), 0.85))::text
                        ELSE ST_AsGeoJSON(
                            (ST_Buffer(ST_Collect(v.geom)::geography, 50))::geometry
                        )::text
                   END AS polygon
            FROM reach r
            JOIN geo_road_vertices v ON v.node_id = r.node AND v.generation = $4
            """,
            [edges_sql, start_vid, minutes * 60, generation],
            using="geo",
        )
        row = rows[0]
        polygon = row["polygon"]
        return GeoIsochroneResponse(
            polygon=json.loads(str(polygon)) if polygon else None,
            reachable_vertices=int(row["vertices"]),
        )


def _two_opt_order(durations: list[list[float | None]], n: int) -> list[int]:
    """Порядок цикла 0→точки→0: nearest neighbor + 2-opt, детерминированно.

    ``durations[i][j] is None`` — недостижимая пара, трактуется бесконечностью.
    """
    inf = float("inf")

    def cost(i: int, j: int) -> float:
        v = durations[i][j]
        return v if v is not None else inf

    unvisited = set(range(1, n))
    order = [0]
    while unvisited:
        last = order[-1]
        nxt = min(unvisited, key=lambda j: (cost(last, j), j))
        order.append(nxt)
        unvisited.remove(nxt)

    def tour_cost(seq: list[int]) -> float:
        cyc = [*seq, seq[0]]
        return sum(cost(cyc[i], cyc[i + 1]) for i in range(len(cyc) - 1))

    improved = True
    while improved:
        improved = False
        for i in range(1, len(order) - 1):
            for j in range(i + 1, len(order)):
                cand = [*order[:i], *reversed(order[i : j + 1]), *order[j + 1 :]]
                if tour_cost(cand) < tour_cost(order) - 1e-9:
                    order = cand
                    improved = True
    return order
