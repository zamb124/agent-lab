"""Дорожный роутинг поверх pgRouting и таблиц ``geo_road_*``.

Контракт графа — миграции ``geo/0001``+``geo/0002``: рёбра хранят стоимость
в секундах по профилям ``car``/``foot``/``bike``/``scooter`` (``-1`` —
направление запрещено). ``bike``/``scooter`` — гибридные лёгкие режимы:
движок импорта разрешает им и проезжую часть (без motor-классов), и
path/footway/steps — dijkstra сама выбирает самое быстрое, пробок нет.
``edges_sql`` pgRouting собирается под режим и активное поколение (int
литералом в тексте — placeholders внутри ``edges_sql`` pgr не связывает).
Snap идёт к ближайшему ПРОХОДИМОМУ для режима ребру (не к вершине моторного
графа — иначе пешеход «прилипает» к магистрали). Порядок TSP — NN+2-opt
поверх матрицы pgRouting, детерминированно.
"""

from __future__ import annotations

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
from core.errors.boundary import PlatformNotFoundError, PlatformUnavailableError


class GeoRoutingError(Exception):
    """Ошибка ввода/лимитов роутинга; ``code`` — platform error_code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code: str = code


_EARTH_R = 6_371_000.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * _EARTH_R * asin(sqrt(a))


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


_FORBIDDEN = "1e12::float8"


def _turn_restrictions_sql(generation: int) -> str:
    """SQL-набор запретов поворотов (pgRouting 4.0: ``path`` + ``cost``).

    Сырые ссылки ``geo_turn_restrictions`` резолвятся в id ребёр джойном
    к ``geo_road_edges`` того же поколения: ``via``-узел — пересечение
    ``from``-way и ``to``-way. Ребро участвует в обеих ролях прохода
    (подъезд к via вперёд по cost или назад по reverse_cost, выезд — то
    же), поэтому односторонние направления не теряются. ``no_*``/
    ``no_entry``/``no_exit`` — запрет ``[from_edge, to_edge]``;
    ``only_*`` — запрет всех выездов с via, кроме ``to_way``. Через-way
    рестрикции (``via_way``) пока не резолвятся — в выборку не попадают.
    """
    # pgRouting 4.0: ``cost`` рестрикции — штраф к стоимости пути, а не
    # булев запрет; -1 сделал бы запрещённый поворот дешевле. Огромный
    # штраф ≈ запрет: объезд выбирается всегда, но если объезда нет,
    # маршрут всё же находится (лучше гигантского ETA, чем route_not_found).
    fwd = (
        "((f.target = r.via_node AND f.car_cost > 0)"
        + " OR (f.source = r.via_node AND f.car_reverse_cost > 0))"
    )
    dep = (
        "((t.source = r.via_node AND t.car_cost > 0)"
        + " OR (t.target = r.via_node AND t.car_reverse_cost > 0))"
    )
    join_from = (
        "JOIN geo_road_edges f ON f.generation = r.generation"
        + " AND f.osm_way_id = r.from_way AND " + fwd
    )
    join_to = (
        "JOIN geo_road_edges t ON t.generation = r.generation"
        + " AND t.osm_way_id = r.to_way AND " + dep
    )
    join_to_others = join_to.replace(
        "t.osm_way_id = r.to_way", "t.osm_way_id <> r.to_way"
    )
    where = f"r.generation = {generation} AND r.via_node IS NOT NULL"
    select = (
        f"SELECT ARRAY[f.id, t.id]::bigint[] AS path, {_FORBIDDEN} AS cost"
        + " FROM geo_turn_restrictions r "
        + join_from
        + " "
    )
    return (
        select
        + join_to
        + f" WHERE {where} AND r.restriction NOT LIKE 'only\\_%'"
        + " UNION ALL "
        + select
        + join_to_others
        + f" WHERE {where} AND r.restriction LIKE 'only\\_%'"
    )


def _barriers_sql(generation: int, mode: str) -> str:
    """SQL-набор запрещённых проходов сквозь барьеры для режима.

    Барьер закрывает транзит через свой узел: пары [въезжающее ребро,
    выезжающее ребро] со штрафом. Въезд/выезд считаются по обеим
    ориентациям ребра (cost/reverse_cost режима). Разворот на том же
    ребре (``t.id <> f.id``) не запрещается — до шлагбаума-тупика
    доехать и развернуться можно.
    """
    cost_col, rcost_col = _mode_columns(mode)
    inc = (
        f"((f.target = b.osm_node_id AND f.{cost_col} > 0)"
        + f" OR (f.source = b.osm_node_id AND f.{rcost_col} > 0))"
    )
    out = (
        f"((t.source = b.osm_node_id AND t.{cost_col} > 0)"
        + f" OR (t.target = b.osm_node_id AND t.{rcost_col} > 0))"
    )
    return (
        f"SELECT ARRAY[f.id, t.id]::bigint[] AS path, {_FORBIDDEN} AS cost"
        + " FROM geo_barriers b"
        + " JOIN geo_road_edges f ON f.generation = b.generation AND " + inc
        + " JOIN geo_road_edges t ON t.generation = b.generation"
        + " AND t.id <> f.id AND " + out
        + f" WHERE b.generation = {generation} AND b.block_{mode}"
    )


def _signals_sql(generation: int, mode: str, delay: float) -> str:
    """SQL-набор штрафов за проезд светофора — транзитные пары [въезд, выезд].

    Механика та же, что у барьеров, но ``cost`` — задержка в секундах
    (``signal_delay_s[mode]``), а не запрет: светофор делает поворот
    дороже, объезд без сигнала может оказаться быстрее.
    """
    cost_col, rcost_col = _mode_columns(mode)
    inc = (
        f"((f.target = s.osm_node_id AND f.{cost_col} > 0)"
        + f" OR (f.source = s.osm_node_id AND f.{rcost_col} > 0))"
    )
    out = (
        f"((t.source = s.osm_node_id AND t.{cost_col} > 0)"
        + f" OR (t.target = s.osm_node_id AND t.{rcost_col} > 0))"
    )
    return (
        f"SELECT ARRAY[f.id, t.id]::bigint[] AS path, {delay}::float8 AS cost"
        + " FROM geo_traffic_signals s"
        + " JOIN geo_road_edges f ON f.generation = s.generation AND " + inc
        + " JOIN geo_road_edges t ON t.generation = s.generation"
        + " AND t.id <> f.id AND " + out
        + f" WHERE s.generation = {generation}"
    )


def _restrictions_sql(generation: int, mode: str, signal_delay: float) -> str:
    """TRSP-ограничения режима: повороты (car), барьеры, штрафы светофоров."""
    union = _barriers_sql(generation, mode)
    if signal_delay > 0:
        union += " UNION ALL " + _signals_sql(generation, mode, signal_delay)
    if mode == "car":
        union = _turn_restrictions_sql(generation) + " UNION ALL " + union
    # Единый внешний вид restrictions_sql: (id, path, cost) —
    # требование и pgr_trsp, и pgr_trsp_withPoints.
    return f"SELECT ROW_NUMBER() OVER () AS id, u.path, u.cost FROM ({union}) u"


_MODE_COLUMNS: dict[str, tuple[str, str]] = {
    "car": ("car_cost", "car_reverse_cost"),
    "foot": ("foot_cost", "foot_reverse_cost"),
    "bike": ("bike_cost", "bike_reverse_cost"),
    "scooter": ("scooter_cost", "scooter_reverse_cost"),
}


def _mode_columns(mode: str) -> tuple[str, str]:
    cols = _MODE_COLUMNS.get(mode)
    if cols is None:
        raise GeoRoutingError("route_mode_unknown", f"Unknown route mode {mode!r}")
    return cols


# Точечный маршрут идёт через TRSP-withPoints: концы привязываются к доле
# вдоль ближайшего ребра (fraction), а не к вершине — и стоимость, и
# геометрия учитывают только пройденную часть крайних рёбер. Запреты
# поворотов и барьеры — часть стоимости маршрута. ``path`` pgr возвращает
# реальные edge id даже для частичных ног; граничные ряды имеют
# node = -1/-2 (точки из points_sql, pgRouting 4.0: vid = -pid).
# Матрица/изохроны остаются на dijkstra-семействе и vertex-snap — пакетные
# запросы без учёта поворотов, барьеров и долей ребра.
#
# legs: frac_from/frac_to — доли ребра, пройденные ногой; backward — езда
# против направления геометрии (reverse_cost и/или точка слева/справа).
_ROUTE_SQL_WP = """
    WITH path AS (
        SELECT path_seq, node, edge, cost,
               LEAD(node) OVER (ORDER BY path_seq) AS next_node
        FROM pgr_trsp_withPoints($1, $2, $3, -1, -2, 'b', directed => true)
    ),
    legs AS (
        SELECT p.path_seq, e.geom, e.length_m,
            CASE
                WHEN p.node = -1 AND p.next_node = -2
                    THEN LEAST($5::float8, $6::float8)
                WHEN p.node = -1 AND p.next_node = e.target THEN $5::float8
                WHEN p.next_node = -2 AND p.node = e.target THEN $6::float8
                ELSE 0.0
            END AS frac_from,
            CASE
                WHEN p.node = -1 AND p.next_node = -2
                    THEN GREATEST($5::float8, $6::float8)
                WHEN p.node = -1 AND p.next_node = e.source THEN $5::float8
                WHEN p.next_node = -2 AND p.node = e.source THEN $6::float8
                ELSE 1.0
            END AS frac_to,
            CASE
                WHEN p.node = -1 AND p.next_node = -2 THEN $5::float8 > $6::float8
                WHEN p.node = -1 THEN p.next_node <> e.target
                ELSE p.node = e.target
            END AS backward
        FROM path p
        JOIN geo_road_edges e ON e.id = p.edge AND e.generation = $4
        WHERE p.edge > 0
    )
    SELECT COUNT(*) AS legs,
           COALESCE(SUM(l.length_m * (l.frac_to - l.frac_from)), 0) AS distance_m,
           COALESCE((SELECT SUM(cost) FROM path), 0) AS duration_s,
           ST_AsGeoJSON(
               ST_LineMerge(ST_Collect(
                   CASE WHEN l.backward
                        THEN ST_Reverse(ST_LineSubstring(l.geom, l.frac_from, l.frac_to))
                        ELSE ST_LineSubstring(l.geom, l.frac_from, l.frac_to)
                   END ORDER BY l.path_seq
               ))
           )::text AS geometry,
           COALESCE(
               (SELECT l2.backward FROM legs l2 ORDER BY l2.path_seq DESC LIMIT 1),
               false
           ) AS arrival_backward
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
    sx: float  # координаты точки привязки на ребре
    sy: float
    tx: float  # касательная ребра (направление source→target) у точки привязки
    ty: float


class _RouteRow(BaseModel):
    legs: int
    distance_m: float
    duration_s: float
    geometry: str | None
    arrival_backward: bool = False


class _CostRow(BaseModel):
    start_vid: int
    end_vid: int
    agg_cost: float


class _IsochroneRow(BaseModel):
    vertices: int
    polygon: str | None


class GeoRoutingService:
    """Роутинг: маршрут, матрица, оптимальный порядок, изохрона."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def _snap_vertex(
        self, lat: float, lng: float, *, mode: str, generation: int
    ) -> int:
        """Вершина ближайшего ПРОХОДИМОГО для режима ребра к точке.

        KNN по ``geom`` ребра (индекс, градусы → ближайшее ребро), точная
        дистанция в метрах одним рядом geography; из концов выбирается
        ближайший. Пешеход/самокат так не «прилипают» к магистрали.
        """
        cost_col, rcost_col = _mode_columns(mode)
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
        """
        cost_col, rcost_col = _mode_columns(mode)
        rows = await execute_raw(
            f"""
            SELECT id AS edge_id, source, target, fraction, dist_m,
                   ST_X(snap_pt) AS sx, ST_Y(snap_pt) AS sy,
                   ST_X(to_pt) - ST_X(snap_pt) AS tx,
                   ST_Y(to_pt) - ST_Y(snap_pt) AS ty
            FROM (
                SELECT e.id, e.source, e.target, e.geom,
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
        start = await self._snap_edge(
            from_lat, from_lng, mode=mode, generation=generation
        )
        end = await self._snap_edge(to_lat, to_lng, mode=mode, generation=generation)
        cost_col, rcost_col = _mode_columns(mode)
        edges_sql = _edges_sql(cost_col, rcost_col, generation)
        # pgRouting 4.0: точки объявляются в points_sql с положительным pid,
        # а vid = -pid; side='b' — точка доступна с обеих сторон.
        points_sql = (
            f"SELECT 1::bigint AS pid, {start.edge_id}::bigint AS edge_id,"
            f" {start.fraction}::float8 AS fraction, 'b'::char AS side"
            f" UNION ALL SELECT 2, {end.edge_id}, {end.fraction}, 'b'"
        )
        rows = await execute_raw(
            _ROUTE_SQL_WP,
            [
                edges_sql,
                _restrictions_sql(
                    generation, mode, self._settings.signal_delay_s.get(mode, 0.0)
                ),
                points_sql,
                generation,
                start.fraction,
                end.fraction,
            ],
            using="geo",
        )
        row = _RouteRow.model_validate(rows[0])
        if row.legs == 0:
            raise PlatformNotFoundError(
                "No route between points", error_code="route_not_found"
            )
        return GeoRouteResponse(
            distance_m=row.distance_m,
            duration_s=row.duration_s,
            geometry=json.loads(row.geometry) if row.geometry else None,
            arrival_side=self._side_of_street(
                end, to_lat, to_lng, backward=row.arrival_backward
            ),
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
            await self._snap_vertex(lat, lng, mode=mode, generation=generation)
            for lat, lng in sources
        ]
        dst_vids = [
            await self._snap_vertex(lat, lng, mode=mode, generation=generation)
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
        vids = "{" + ",".join(str(v) for v in sorted({*src_vids, *dst_vids})) + "}"
        rows = await execute_raw(
            """
            SELECT start_vid, end_vid, agg_cost
            FROM pgr_dijkstraCostMatrix($1, $2::bigint[], true)
            """,
            [edges_sql, vids],
            using="geo",
        )
        table: dict[tuple[int, int], float] = {}
        for r in rows:
            cell = _CostRow.model_validate(r)
            table[(cell.start_vid, cell.end_vid)] = cell.agg_cost
        return [
            [0.0 if sv == dv else table.get((sv, dv)) for dv in dst_vids]
            for sv in src_vids
        ]

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
        start_vid = await self._snap_vertex(lat, lng, mode=mode, generation=generation)
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
