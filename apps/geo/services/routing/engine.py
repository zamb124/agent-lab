"""In-memory роутинг-движок geo.

``GeoRoutingEngine`` держит собранные ``ModeGraphs`` по режимам и
перестраивает их при смене поколения импорта или инвалидации правок
админа. Все маршрутные запросы идут по графу — pgRouting/SQL-роутинг
полностью заменён; граф не построился — запрос падает, фолбеков нет.

Семантика запросов идентична бывшему pgr-контуру: ``path`` — TRSP
с долями крайних рёбер и штрафами переходов, ``costs`` — dijkstra-матрица
по vertex-snap, ``reachable`` — driving distance с cutoff.

Скалярный доступ к массивам — ``memoryview``/``bisect``: индексация
``ndarray`` в numpy-стабах типизирована как ``Any``.
"""

from __future__ import annotations

import asyncio
import bisect
from dataclasses import dataclass

import numpy as np
from scipy.sparse.csgraph import dijkstra

from apps.geo.config import GeoSettings
from apps.geo.services.routing.builder import build_mode_graphs
from apps.geo.services.routing.graph import ModeGraphs, edge_at


class GeoRoutingError(Exception):
    """Ошибка ввода/лимитов роутинга; ``code`` — platform error_code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code: str = code


@dataclass(frozen=True, slots=True)
class EdgePoint:
    """Точка, привязанная к доле ``fraction`` вдоль проходимого ребра."""

    edge_id: int
    source: int  # pgr vertex id (node_id) конца ребра
    target: int
    fraction: float
    cost: float  # forward source→target, сек; <=0 — направление закрыто
    rcost: float  # reverse target→source, сек


@dataclass(frozen=True, slots=True)
class PathLeg:
    """Плечо пути: доля ребра и езда против ориентации его геометрии."""

    edge_id: int
    frac_from: float
    frac_to: float
    backward: bool


@dataclass(frozen=True, slots=True)
class PathResult:
    """Путь: плечи для сборки геометрии и стоимость в секундах."""

    total_cost: float
    legs: list[PathLeg]


def _vidx(vids_v: memoryview, vid: int) -> int | None:
    """Base-индекс вершины по node_id; ``None`` — вершина вне графа."""
    pos = bisect.bisect_left(vids_v, vid)
    if pos >= len(vids_v) or vids_v[pos] != vid:
        return None
    return pos


class GeoRoutingEngine:
    """Кэш CSR-графов по режимам маршрута; перестройка лениво под lock."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings
        self._graphs: dict[str, tuple[ModeGraphs, int]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._epoch: int = 0

    def invalidate(self) -> None:
        """Входные данные графа изменились (правки админа) — пересборка."""
        self._epoch += 1

    async def graph(self, mode: str, generation: int) -> ModeGraphs:
        """Граф режима на поколение; строится лениво, своп — по generation."""
        entry = self._graphs.get(mode)
        if (
            entry is not None
            and entry[0].generation == generation
            and entry[1] == self._epoch
        ):
            return entry[0]
        async with self._lock:
            entry = self._graphs.get(mode)
            if (
                entry is not None
                and entry[0].generation == generation
                and entry[1] == self._epoch
            ):
                return entry[0]
            built = await build_mode_graphs(mode, generation, self._settings)
            self._graphs[mode] = (built, self._epoch)
            return built

    def path(
        self, g: ModeGraphs, start: EdgePoint, end: EdgePoint
    ) -> PathResult | None:
        """Кратчайший путь точка-точка с долями крайних рёбер (TRSP-паритет).

        Виртуальные входы: выезд с точки старта в обе стороны её ребра
        стоит пропорциональную долю; вход в точку финиша — с концов её
        ребра. Гаджет-граф — штрафы поворотов/барьеров/светофоров в переходах.
        """
        vids_v: memoryview = memoryview(g.vertex_ids)
        succ: list[tuple[int, float, bool]] = []  # node, cost, выезд к target-концу
        if start.cost > 0:
            succ.append(
                (
                    g.arrival(_req_vidx(vids_v, start.target), start.edge_id),
                    (1.0 - start.fraction) * start.cost,
                    True,
                )
            )
        if start.rcost > 0:
            succ.append(
                (
                    g.arrival(_req_vidx(vids_v, start.source), start.edge_id),
                    start.fraction * start.rcost,
                    False,
                )
            )
        preds: list[tuple[int, float, bool]] = []  # node, cost, въезд со source-конца
        if end.cost > 0:
            preds.append(
                (
                    g.departure(_req_vidx(vids_v, end.source), end.edge_id),
                    end.fraction * end.cost,
                    True,
                )
            )
        if end.rcost > 0:
            preds.append(
                (
                    g.departure(_req_vidx(vids_v, end.target), end.edge_id),
                    (1.0 - end.fraction) * end.rcost,
                    False,
                )
            )
        if not succ or not preds:
            return None
        dist, pred = dijkstra(
            g.full_time.csr,
            directed=True,
            indices=[n for n, _, _ in succ],
            return_predecessors=True,
        )
        dist_mv: memoryview = memoryview(dist.reshape(-1))
        pred_mv: memoryview = memoryview(pred.reshape(-1))
        ncol = dist.shape[1]
        best = np.inf
        bi = bj = -1
        for k, (_, sc, _) in enumerate(succ):
            for j, (tn, pc, _) in enumerate(preds):
                c = sc + dist_mv[k * ncol + tn] + pc
                if c < best:
                    best, bi, bj = c, k, j
        direct = _direct_same_edge(start, end)
        if best == np.inf:
            return direct
        if direct is not None and direct.total_cost <= best:
            return direct
        src_node, _, fwd_start = succ[bi]
        dst_node, _, fwd_end = preds[bj]
        edge_ids = self._reconstruct(g, pred_mv, bi * ncol, src_node, dst_node)
        legs = [_start_leg(start, fwd_start)]
        legs.extend(PathLeg(eid, 0.0, 1.0, back) for eid, back in edge_ids)
        legs.append(_end_leg(end, fwd_end))
        return PathResult(total_cost=best, legs=legs)

    def _reconstruct(
        self,
        g: ModeGraphs,
        pred_mv: memoryview,
        row_off: int,
        src_node: int,
        dst_node: int,
    ) -> list[tuple[int, bool]]:
        """Цепочка edge_id пути по predecessor-дереву; переходы пропускаются."""
        chain: list[tuple[int, int]] = []
        cur = dst_node
        while cur != src_node:
            prev = pred_mv[row_off + cur]
            if prev < 0:
                raise GeoRoutingError(
                    "route_graph_inconsistent",
                    "Predecessor chain broke before the source node",
                )
            chain.append((prev, cur))
            cur = prev
        chain.reverse()
        edges: list[tuple[int, bool]] = []
        for a, b in chain:
            eid, back = edge_at(g.full_time, a, b)
            if eid >= 0:
                edges.append((eid, back))
        return edges

    def costs(
        self,
        g: ModeGraphs,
        src_vids: list[int],
        dst_vids: list[int],
        *,
        metric: str,
    ) -> list[list[float | None]]:
        """Матрица стоимости vertex→vertex по plain-графу режима."""
        csr = g.plain_time.csr if metric == "time" else g.plain_dist.csr
        vids_v: memoryview = memoryview(g.vertex_ids)
        src_idx = [_vidx(vids_v, v) for v in src_vids]
        dst_idx = [_vidx(vids_v, v) for v in dst_vids]
        uniq = sorted({i for i in src_idx if i is not None})
        if not uniq:
            return [[None] * len(dst_vids) for _ in src_vids]
        dist = dijkstra(csr, directed=True, indices=uniq)
        dist_mv: memoryview = memoryview(dist.reshape(-1))
        ncol = dist.shape[1]
        row_of = {v: k for k, v in enumerate(uniq)}
        table: dict[tuple[int, int], float] = {}
        for sv, si in zip(src_vids, src_idx):
            if si is None:
                continue
            for dv, di in zip(dst_vids, dst_idx):
                if di is None:
                    continue
                c = dist_mv[row_of[si] * ncol + di]
                if c < np.inf:
                    table[(sv, dv)] = c
        return [
            [0.0 if sv == dv else table.get((sv, dv)) for dv in dst_vids]
            for sv in src_vids
        ]

    def reachable(self, g: ModeGraphs, start_vid: int, cutoff_s: float) -> list[int]:
        """node_id вершин, достижимых за ``cutoff_s`` секунд (plain-граф)."""
        i = _vidx(memoryview(g.vertex_ids), start_vid)
        if i is None:
            return []
        flat = dijkstra(
            g.plain_time.csr, directed=True, indices=[i], limit=cutoff_s
        ).reshape(-1)
        reached = flat < np.inf
        return list(memoryview(g.vertex_ids[reached]))


def _req_vidx(vids_v: memoryview, vid: int) -> int:
    """Base-индекс конца snap-ребра; вне графа — ошибка данных."""
    idx = _vidx(vids_v, vid)
    if idx is None:
        raise GeoRoutingError(
            "route_graph_inconsistent",
            f"Snapped vertex {vid} is absent from the built road graph",
        )
    return idx


def _direct_same_edge(start: EdgePoint, end: EdgePoint) -> PathResult | None:
    """Проезд внутри одного ребра без захода в вершину."""
    if start.edge_id != end.edge_id:
        return None
    f_s, f_t = start.fraction, end.fraction
    direct: PathResult | None = None
    if f_t >= f_s and start.cost > 0:
        direct = PathResult(
            total_cost=(f_t - f_s) * start.cost,
            legs=[PathLeg(start.edge_id, f_s, f_t, False)],
        )
    if f_s > f_t and start.rcost > 0:
        cost = (f_s - f_t) * start.rcost
        if direct is None or cost < direct.total_cost:
            direct = PathResult(
                total_cost=cost,
                legs=[PathLeg(start.edge_id, f_t, f_s, True)],
            )
    return direct


def _start_leg(p: EdgePoint, forward: bool) -> PathLeg:
    if forward:
        return PathLeg(p.edge_id, p.fraction, 1.0, False)
    return PathLeg(p.edge_id, 0.0, p.fraction, True)


def _end_leg(p: EdgePoint, from_source: bool) -> PathLeg:
    if from_source:
        return PathLeg(p.edge_id, 0.0, p.fraction, False)
    return PathLeg(p.edge_id, p.fraction, 1.0, True)
