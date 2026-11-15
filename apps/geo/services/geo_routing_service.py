"""Дорожный роутинг поверх in-memory графа ``routing/`` и PostGIS.

Стоимости и путь считает ``GeoRoutingEngine`` (CSR-граф поколения,
gadget-переходы для рестрикций/барьеров/светофоров); Postgres остаётся
источником данных и выполняет пространственную часть: KNN-snap точек к
проходимым рёбрам и сборку геометрии ответа (``ST_LineSubstring`` по
плечам). Порядок TSP — NN+2-opt поверх матрицы движка, детерминированно.
"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Literal

from oxyde import execute_raw
from pydantic import BaseModel

from apps.geo.config import GeoSettings
from apps.geo.models.api import (
    GeoIsochroneResponse,
    GeoRouteLeg,
    GeoRouteMatrixResponse,
    GeoRouteOrderResponse,
    GeoRouteResponse,
)
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.services.routing.builder import MODE_COLUMNS
from apps.geo.services.routing.engine import (
    EdgePoint,
    GeoRoutingEngine,
    GeoRoutingError,
    PathResult,
)
from core.errors.boundary import PlatformNotFoundError, PlatformUnavailableError

__all__ = ["GeoRoutingError", "GeoRoutingService"]

_EARTH_R = 6_371_000.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return 2 * _EARTH_R * math.asin(math.sqrt(a))


# Плечи пути приходят из движка массивами: edge_id / доля / направление.
# Геометрия и дистанция собираются тем же выражением, что было в TRSP:
# substring доли ребра, reverse для обратного направления, LineMerge.
_LEGS_SQL = """
    WITH legs AS (
        SELECT l.ord, e.geom, e.length_m, l.frac_from, l.frac_to, l.backward
        FROM UNNEST(
               string_to_array($1, ',')::bigint[],
               string_to_array($2, ',')::float8[],
               string_to_array($3, ',')::float8[],
               string_to_array($4, ',')::bool[])
             WITH ORDINALITY AS l(edge_id, frac_from, frac_to, backward, ord)
        JOIN geo_road_edges e ON e.id = l.edge_id AND e.generation = $5
    )
    SELECT COUNT(*) AS legs,
           COALESCE(SUM(l.length_m * (l.frac_to - l.frac_from)), 0) AS distance_m,
           ST_AsGeoJSON(
               ST_LineMerge(ST_Collect(
                   CASE WHEN l.backward
                        THEN ST_Reverse(ST_LineSubstring(l.geom, l.frac_from, l.frac_to))
                        ELSE ST_LineSubstring(l.geom, l.frac_from, l.frac_to)
                   END ORDER BY l.ord
               ))
           )::text AS geometry
    FROM legs l
"""


class _SnapRow(BaseModel):
    source: int
    target: int
    src_lat: float
    src_lng: float
    dst_lat: float
    dst_lng: float
    dist_m: float


class _EdgeSnap(BaseModel):
    """Привязка точки к доле вдоль ребра + касательная у точки привязки."""

    edge_id: int
    source: int
    target: int
    fraction: float
    dist_m: float
    cost: float
    rcost: float
    sx: float  # координаты точки привязки на ребре
    sy: float
    tx: float  # касательная ребра (направление source→target) у точки привязки
    ty: float


class _RouteRow(BaseModel):
    legs: int
    distance_m: float
    geometry: str | None


class _IsochroneRow(BaseModel):
    vertices: int
    polygon: str | None


class GeoRoutingService:
    """Роутинг: маршрут, матрица, оптимальный порядок, изохрона."""

    def __init__(self, settings: GeoSettings, engine: GeoRoutingEngine) -> None:
        self._settings: GeoSettings = settings
        self._engine: GeoRoutingEngine = engine

    async def _snap_vertex(
        self, lat: float, lng: float, *, mode: str, generation: int
    ) -> int:
        """Вершина ближайшего ПРОХОДИМОГО для режима ребра к точке.

        KNN по ``geom`` ребра (индекс, градусы → ближайшее ребро), точная
        дистанция в метрах одним рядом geography; из концов выбирается
        ближайший. Пешеход/самокат так не «прилипают» к магистрали.
        """
        cost_col, rcost_col = MODE_COLUMNS[mode]
        rows = await execute_raw(
            f"""
            SELECT source, target, src_lat, src_lng, dst_lat, dst_lng,
                   ST_Distance(
                       geom::geography,
                       ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                   ) AS dist_m
            FROM geo_road_edges
            WHERE generation = $3 AND ({cost_col} > 0 OR {rcost_col} > 0)
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
            LIMIT 1
            """,
            [lng, lat, generation],
            using="geo",
        )
        if not rows:
            raise PlatformUnavailableError(
                f"Road graph has no {mode}-passable edges — run OSM import",
                error_code="geo_import_unavailable",
            )
        edge = _SnapRow.model_validate(rows[0])
        if edge.dist_m > self._settings.snap_max_distance_m:
            raise GeoRoutingError(
                "point_too_far_from_road",
                f"Point is {edge.dist_m:.0f}m from the {mode} road graph",
            )
        src_d = _haversine_m(lat, lng, edge.src_lat, edge.src_lng)
        dst_d = _haversine_m(lat, lng, edge.dst_lat, edge.dst_lng)
        return edge.source if src_d <= dst_d else edge.target

    async def _snap_edge(
        self, lat: float, lng: float, *, mode: str, generation: int
    ) -> _EdgeSnap:
        """Ближайшее проходимое ребро + доля вдоль геометрии (fraction).

        Касательная ``tx/ty`` — локальное направление source→target у точки
        привязки (интерполяция до/после fraction); нужна для стороны улицы.
        Стоимости ребра возвращаются вместе со snap — виртуальные входы
        движка тарифицируют пройденную долю.
        """
        cost_col, rcost_col = MODE_COLUMNS[mode]
        rows = await execute_raw(
            f"""
            SELECT id AS edge_id, source, target, fraction, dist_m,
                   {cost_col} AS cost, {rcost_col} AS rcost,
                   ST_X(snap_pt) AS sx, ST_Y(snap_pt) AS sy,
                   ST_X(to_pt) - ST_X(snap_pt) AS tx,
                   ST_Y(to_pt) - ST_Y(snap_pt) AS ty
            FROM (
                SELECT e.id, e.source, e.target, e.geom,
                       e.{cost_col}, e.{rcost_col},
                       ST_LineLocatePoint(e.geom, q.g) AS fraction,
                       ST_Distance(e.geom::geography, q.g::geography) AS dist_m,
                       ST_LineInterpolatePoint(e.geom,
                           GREATEST(ST_LineLocatePoint(e.geom, q.g) - 0.001, 0.0)
                       ) AS snap_pt,
                       ST_LineInterpolatePoint(e.geom,
                           LEAST(ST_LineLocatePoint(e.geom, q.g) + 0.001, 1.0)
                       ) AS to_pt
                FROM geo_road_edges e,
                     (SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326) AS g) q
                WHERE e.generation = $3 AND ({cost_col} > 0 OR {rcost_col} > 0)
                ORDER BY e.geom <-> q.g
                LIMIT 1
            ) s
            """,
            [lng, lat, generation],
            using="geo",
        )
        if not rows:
            raise PlatformUnavailableError(
                f"Road graph has no {mode}-passable edges — run OSM import",
                error_code="geo_import_unavailable",
            )
        snap = _EdgeSnap.model_validate(rows[0])
        if snap.dist_m > self._settings.snap_max_distance_m:
            raise GeoRoutingError(
                "point_too_far_from_road",
                f"Point is {snap.dist_m:.0f}m from the {mode} road graph",
            )
        return snap

    @staticmethod
    def _side_of_street(
        snap: _EdgeSnap, lat: float, lng: float, *, backward: bool
    ) -> Literal["left", "right"] | None:
        """Сторона улицы точки относительно направления движения в конце пути.

        cross>0 — точка слева от касательной source→target; при езде против
        направления ребра сторона зеркалится. Вырожденная касательная
        (привязка точно к вершине) → None.
        """
        norm = math.hypot(snap.tx, snap.ty)
        if norm == 0.0:
            return None
        # Нормированный cross — расстояние точки от касательной в градусах
        # (~1e-8 ≈ миллиметр): порог отсеивает только вырожденные привязки.
        cross = (snap.tx * (lat - snap.sy) - snap.ty * (lng - snap.sx)) / norm
        if abs(cross) < 1e-8:
            return None
        left = cross > 0
        if backward:
            left = not left
        return "left" if left else "right"

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
        start_snap, end_snap, g = await asyncio.gather(
            self._snap_edge(from_lat, from_lng, mode=mode, generation=generation),
            self._snap_edge(to_lat, to_lng, mode=mode, generation=generation),
            self._engine.graph(mode, generation),
        )
        start = self._edge_point(start_snap)
        end = self._edge_point(end_snap)
        path = await asyncio.to_thread(self._engine.path, g, start, end)
        if path is None:
            raise PlatformNotFoundError(
                "No route between points", error_code="route_not_found"
            )
        row = await self._assemble_geometry(path, generation)
        return GeoRouteResponse(
            distance_m=row.distance_m,
            duration_s=path.total_cost,
            geometry=json.loads(row.geometry) if row.geometry else None,
            arrival_side=self._side_of_street(
                end_snap, to_lat, to_lng, backward=path.legs[-1].backward
            ),
        )

    @staticmethod
    def _edge_point(snap: _EdgeSnap) -> EdgePoint:
        return EdgePoint(
            edge_id=snap.edge_id,
            source=snap.source,
            target=snap.target,
            fraction=snap.fraction,
            cost=snap.cost,
            rcost=snap.rcost,
        )

    async def _assemble_geometry(
        self, path: PathResult, generation: int
    ) -> _RouteRow:
        """Геометрия и дистанция пути по плечам движка — PostGIS-сборка."""
        rows = await execute_raw(
            _LEGS_SQL,
            [
                ",".join(str(leg.edge_id) for leg in path.legs),
                ",".join(str(leg.frac_from) for leg in path.legs),
                ",".join(str(leg.frac_to) for leg in path.legs),
                ",".join("t" if leg.backward else "f" for leg in path.legs),
                generation,
            ],
            using="geo",
        )
        return _RouteRow.model_validate(rows[0])

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
            await self._snap_vertex(lat, lng, mode=mode, generation=generation)
            for lat, lng in sources
        ]
        dst_vids = [
            await self._snap_vertex(lat, lng, mode=mode, generation=generation)
            for lat, lng in targets
        ]
        g = await self._engine.graph(mode, generation)
        durations, distances = await asyncio.gather(
            asyncio.to_thread(
                self._engine.costs, g, src_vids, dst_vids, metric="time"
            ),
            asyncio.to_thread(
                self._engine.costs, g, src_vids, dst_vids, metric="distance"
            ),
        )
        return GeoRouteMatrixResponse(durations_s=durations, distances_m=distances)

    async def optimal_order(
        self,
        *,
        start: tuple[float, float],
        points: list[tuple[float, float]],
        mode: str,
        with_legs: bool,
    ) -> GeoRouteOrderResponse:
        """Порядок объезда: NN + 2-opt по матрице движка, детерминированно."""
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
        start_vid = await self._snap_vertex(lat, lng, mode=mode, generation=generation)
        g = await self._engine.graph(mode, generation)
        node_ids = await asyncio.to_thread(
            self._engine.reachable, g, start_vid, minutes * 60
        )
        rows = await execute_raw(
            """
            SELECT COUNT(*) AS vertices,
                   CASE WHEN COUNT(*) >= 3
                        THEN ST_AsGeoJSON(ST_ConcaveHull(ST_Collect(v.geom), 0.85))::text
                        ELSE ST_AsGeoJSON(
                            (ST_Buffer(ST_Collect(v.geom)::geography, 50))::geometry
                        )::text
                   END AS polygon
            FROM geo_road_vertices v
            WHERE v.generation = $2
              AND v.node_id = ANY(string_to_array($1, ',')::bigint[])
            """,
            [",".join(str(n) for n in node_ids), generation],
            using="geo",
        )
        row = _IsochroneRow.model_validate(rows[0])
        return GeoIsochroneResponse(
            polygon=json.loads(row.polygon) if row.polygon else None,
            reachable_vertices=row.vertices,
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
