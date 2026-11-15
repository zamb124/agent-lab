"""Сборка ``ModeGraphs`` из Postgres одним проходом.

Данные грузятся ``array_to_json(array_agg(...))``-выборками (колонки
списками — без миллионов dict-рядов; голый ``array_agg`` мост Oxyde
не декодирует и отдаёт NULL); сырой ``dict[str, Any]`` результата сразу
санитизируется в типизированные массивы — это граница Any→typed. CPU-сборка идёт в
``asyncio.to_thread`` — event loop не стоит. Гаджеты разворачивают только
вершины с семантикой переходов: барьеры режима, светофоры (при
``signal_delay_s[mode] > 0``) и via-узлы рестрикций (car).

Скалярный доступ к массивам — через ``memoryview``: индексация
``ndarray`` в numpy-стабах типизирована как ``Any``.
"""

from __future__ import annotations

import asyncio

import numpy as np
import numpy.typing as npt
from oxyde import execute_raw
from scipy.sparse import csr_matrix

from apps.geo.config import GeoSettings
from apps.geo.services.routing.graph import FORBIDDEN, CsrGraph, ModeGraphs
from core.errors.boundary import PlatformUnavailableError
from core.types import SqlParameterValue

MODE_COLUMNS: dict[str, tuple[str, str]] = {
    "car": ("car_cost", "car_reverse_cost"),
    "foot": ("foot_cost", "foot_reverse_cost"),
    "bike": ("bike_cost", "bike_reverse_cost"),
    "scooter": ("scooter_cost", "scooter_reverse_cost"),
}

_i64 = npt.NDArray[np.int64]
_i32 = npt.NDArray[np.int32]
_f64 = npt.NDArray[np.float64]
_bool = npt.NDArray[np.bool_]


def _agg_list(value: SqlParameterValue | list[SqlParameterValue]) -> list[float]:
    """``array_to_json``-колонка → список float; не-список — пустая выборка."""
    if not isinstance(value, list):
        return []
    return [float(str(v)) for v in value]


_Col = SqlParameterValue | list[SqlParameterValue]


async def build_mode_graphs(
    mode: str, generation: int, settings: GeoSettings
) -> ModeGraphs:
    """Сборка графов режима на поколение; пустой граф — ``raise``."""
    cost_col, rcost_col = MODE_COLUMNS[mode]
    rows: list[dict[str, _Col]] = await execute_raw(
        f"""
        SELECT array_to_json(array_agg(id)) AS ids,
               array_to_json(array_agg(source)) AS srcs,
               array_to_json(array_agg(target)) AS dsts,
               array_to_json(array_agg(osm_way_id)) AS ways,
               array_to_json(array_agg(length_m)) AS lens,
               array_to_json(array_agg({cost_col})) AS costs,
               array_to_json(array_agg({rcost_col})) AS rcosts
        FROM geo_road_edges
        WHERE generation = $1 AND ({cost_col} > 0 OR {rcost_col} > 0)
        """,
        [generation],
        using="geo",
    )
    row = rows[0]
    ids = _agg_list(row["ids"])
    if not ids:
        raise PlatformUnavailableError(
            f"Road graph has no {mode}-passable edges — run OSM import",
            error_code="geo_import_unavailable",
        )
    signal_delay = settings.signal_delay_s.get(mode, 0.0)
    signals: set[int] = set()
    if signal_delay > 0:
        signals = await _id_set(
            "SELECT array_to_json(array_agg(osm_node_id)) AS ids FROM geo_traffic_signals"
            + " WHERE generation = $1",
            generation,
        )
    restrictions: list[tuple[int, int, int, str]] = []
    if mode == "car":
        rrows: list[dict[str, _Col]] = await execute_raw(
            """
            SELECT from_way, to_way, via_node, restriction
            FROM geo_turn_restrictions
            WHERE generation = $1 AND via_node IS NOT NULL
            """,
            [generation],
            using="geo",
        )
        restrictions = [
            (
                int(str(r["from_way"])),
                int(str(r["to_way"])),
                int(str(r["via_node"])),
                str(r["restriction"]),
            )
            for r in rrows
        ]
    barriers = await _id_set(
        "SELECT array_to_json(array_agg(osm_node_id)) AS ids FROM geo_barriers"
        + f" WHERE generation = $1 AND block_{mode}",
        generation,
    )
    return await asyncio.to_thread(
        _assemble,
        mode,
        generation,
        np.asarray(ids, dtype=np.int64),
        np.asarray(_agg_list(row["srcs"]), dtype=np.int64),
        np.asarray(_agg_list(row["dsts"]), dtype=np.int64),
        np.asarray(_agg_list(row["ways"]), dtype=np.int64),
        np.asarray(_agg_list(row["lens"]), dtype=np.float64),
        np.asarray(_agg_list(row["costs"]), dtype=np.float64),
        np.asarray(_agg_list(row["rcosts"]), dtype=np.float64),
        barriers,
        signal_delay,
        signals,
        restrictions,
    )


async def _id_set(sql: str, generation: int) -> set[int]:
    rows: list[dict[str, _Col]] = await execute_raw(sql, [generation], using="geo")
    raw = rows[0]["ids"]
    if not isinstance(raw, list):
        return set()
    return {int(str(v)) for v in raw}


def _assemble(
    mode: str,
    generation: int,
    e_ids: _i64,
    e_src: _i64,
    e_dst: _i64,
    e_way: _i64,
    e_len: _f64,
    e_cost: _f64,
    e_rcost: _f64,
    barriers: set[int],
    signal_delay: float,
    signals: set[int],
    restrictions: list[tuple[int, int, int, str]],
) -> ModeGraphs:
    """Чистая CPU-сборка: дуги → вершины → gadget-развёртка → три CSR."""
    fwd = e_cost > 0
    rev = e_rcost > 0
    d_u = np.concatenate([e_src[fwd], e_dst[rev]])
    d_v = np.concatenate([e_dst[fwd], e_src[rev]])
    d_e = np.concatenate([e_ids[fwd], e_ids[rev]])
    d_w = np.concatenate([e_cost[fwd], e_rcost[rev]])
    d_l = np.concatenate([e_len[fwd], e_len[rev]])
    d_back: _bool = np.concatenate(
        [np.zeros(int(fwd.sum()), bool), np.ones(int(rev.sum()), bool)]
    )
    d_way = np.concatenate([e_way[fwd], e_way[rev]])

    vertex_ids = np.unique(np.concatenate([e_src, e_dst]))
    n_base = len(vertex_ids)
    d_ui: _i32 = np.searchsorted(vertex_ids, d_u).astype(np.int32)
    d_vi: _i32 = np.searchsorted(vertex_ids, d_v).astype(np.int32)

    plain_time = _to_csr(d_ui, d_vi, d_w, d_e, d_back, n_base)
    plain_dist = _to_csr(d_ui, d_vi, d_l, d_e, d_back, n_base)

    special = _special_vertices(
        mode, vertex_ids, barriers, signal_delay, signals, restrictions
    )
    full_time, arr_node, dep_node, n_nodes = _expand_gadgets(
        d_ui,
        d_vi,
        d_e,
        d_w,
        d_back,
        d_way,
        n_base,
        special,
        barriers,
        signal_delay,
        signals,
        vertex_ids,
        restrictions,
    )
    return ModeGraphs(
        mode=mode,
        generation=generation,
        vertex_ids=vertex_ids,
        n_base=n_base,
        plain_time=plain_time,
        plain_dist=plain_dist,
        full_time=full_time,
        n_nodes=n_nodes,
        arr_node=arr_node,
        dep_node=dep_node,
    )


def _special_vertices(
    mode: str,
    vertex_ids: _i64,
    barriers: set[int],
    signal_delay: float,
    signals: set[int],
    restrictions: list[tuple[int, int, int, str]],
) -> _i64:
    """Base-индексы вершин, которым нужен edge-state gadget."""
    special = set(barriers)
    if signal_delay > 0:
        special |= signals
    if mode == "car":
        special |= {via for _, _, via, _ in restrictions}
    if not special:
        return np.empty(0, dtype=np.int64)
    s_arr: _i64 = np.fromiter(special, dtype=np.int64)
    pos: npt.NDArray[np.intp] = np.searchsorted(vertex_ids, s_arr)
    present: _bool = np.isin(s_arr, vertex_ids)
    return np.sort(pos[present]).astype(np.int64)


def _to_csr(
    d_ui: _i32,
    d_vi: _i32,
    weights: _f64,
    d_e: _i64,
    d_back: _bool,
    n_nodes: int,
) -> CsrGraph:
    """CSR из дугового списка; дубли (u,v) схлопываются в минимальную цену.

    ``indptr``/``indices``/``data`` собираются вручную — параллельные
    ``edge_id``/``backward`` держат позиционное выравнивание с ``data``.
    """
    key = d_ui.astype(np.int64) * n_nodes + d_vi
    order = np.lexsort((weights, key))
    key_s = key[order]
    first: _bool = np.empty(len(key_s), dtype=bool)
    first[0] = True
    first[1:] = key_s[1:] != key_s[:-1]
    sel = order[first]
    u = d_ui[sel]
    v = d_vi[sel]
    w = weights[sel]
    counts = np.bincount(u + 1, minlength=n_nodes + 1)
    indptr = counts.cumsum(dtype=np.int32)
    return CsrGraph(
        csr=csr_matrix((w, v, indptr), shape=(n_nodes, n_nodes), copy=False),
        indptr=indptr,
        indices=v,
        edge_id=d_e[sel],
        backward=d_back[sel],
    )


def _expand_gadgets(
    d_ui: _i32,
    d_vi: _i32,
    d_e: _i64,
    d_w: _f64,
    d_back: _bool,
    d_way: _i64,
    n_base: int,
    special: _i64,
    barriers: set[int],
    signal_delay: float,
    signals: set[int],
    vertex_ids: _i64,
    restrictions: list[tuple[int, int, int, str]],
) -> tuple[CsrGraph, dict[tuple[int, int], int], dict[tuple[int, int], int], int]:
    """Развёртка special-вершин в vin/vout-полуузлы с переходами-штрафами.

    ``vin`` — «приехал в вершину по конкретному ребру», ``vout`` — «стою
    в вершине, выезжаю по конкретному ребру». Переход vin→vout несёт штраф:
    барьер режима и запрещённый поворот — ``FORBIDDEN`` (u-turn по тому же
    ребру разрешён, как в TRSP), светофор — ``signal_delay``.
    """
    if len(special) == 0:
        return _to_csr(d_ui, d_vi, d_w, d_e, d_back, n_base), {}, {}, n_base

    in_pos: npt.NDArray[np.intp] = np.flatnonzero(np.isin(d_vi, special))
    out_pos: npt.NDArray[np.intp] = np.flatnonzero(np.isin(d_ui, special))
    ins = _group_by_vertex(d_vi, in_pos)
    outs = _group_by_vertex(d_ui, out_pos)

    restr_by_via: dict[int, list[tuple[int, int, str]]] = {}
    for fw, tw, via, kind in restrictions:
        restr_by_via.setdefault(via, []).append((fw, tw, kind))

    d_ui = d_ui.copy()
    d_vi = d_vi.copy()
    d_ui_v = memoryview(d_ui)
    d_vi_v = memoryview(d_vi)
    d_e_v = memoryview(d_e)
    d_way_v = memoryview(d_way)
    special_v = memoryview(special)
    vertex_ids_v = memoryview(vertex_ids)
    tr_u: list[int] = []
    tr_v: list[int] = []
    tr_w: list[float] = []
    arr_node: dict[tuple[int, int], int] = {}
    dep_node: dict[tuple[int, int], int] = {}
    next_idx = n_base
    for v in special_v:
        vid = vertex_ids_v[v]
        vi_in = ins.get(v, [])
        vo_out = outs.get(v, [])
        vin = {i: next_idx + j for j, i in enumerate(vi_in)}
        base_out = next_idx + len(vi_in)
        vout = {i: base_out + j for j, i in enumerate(vo_out)}
        next_idx = base_out + len(vo_out)
        delay = signal_delay if vid in signals else 0.0
        blocked = vid in barriers
        forbid = _forbidden_pairs(restr_by_via.get(vid), vi_in, vo_out, d_way_v)
        for i, ni in vin.items():
            arr_node[(v, d_e_v[i])] = ni
            for j, nj in vout.items():
                same = d_e_v[i] == d_e_v[j]
                pen = 0.0 if same else delay + (FORBIDDEN if blocked else 0.0)
                if (i, j) in forbid:
                    pen += FORBIDDEN
                tr_u.append(ni)
                tr_v.append(nj)
                tr_w.append(pen)
        for i, nj in vout.items():
            dep_node[(v, d_e_v[i])] = nj
        for i, ni in vin.items():
            d_vi_v[i] = ni
        for i, nj in vout.items():
            d_ui_v[i] = nj

    n_nodes = next_idx
    au: _i32 = np.concatenate([d_ui, np.asarray(tr_u, dtype=np.int32)])
    av: _i32 = np.concatenate([d_vi, np.asarray(tr_v, dtype=np.int32)])
    aw: _f64 = np.concatenate([d_w, np.asarray(tr_w, dtype=np.float64)])
    ae: _i64 = np.concatenate([d_e, np.full(len(tr_u), -1, dtype=np.int64)])
    ab: _bool = np.concatenate([d_back, np.zeros(len(tr_u), dtype=bool)])
    g = _to_csr(au, av, aw, ae, ab, n_nodes)
    return g, arr_node, dep_node, n_nodes


def _group_by_vertex(
    vidx: _i32, positions: npt.NDArray[np.intp]
) -> dict[int, list[int]]:
    """Позиции дуг по индексу вершины — сортировка + split, без dict-of-loop."""
    if len(positions) == 0:
        return {}
    order = np.argsort(vidx[positions], kind="stable")
    verts = vidx[positions][order]
    uniq: _i32
    counts: npt.NDArray[np.intp]
    uniq, counts = np.unique(verts, return_counts=True)
    groups: list[npt.NDArray[np.intp]] = np.split(
        positions[order], np.cumsum(counts)[:-1]
    )
    uniq_v: memoryview = memoryview(uniq)
    return {v: _ints(g) for v, g in zip(uniq_v, groups)}


def _ints(arr: npt.NDArray[np.intp]) -> list[int]:
    """Позиции дуг массива → python int (``memoryview`` — zero-copy)."""
    return list(memoryview(arr))


def _forbidden_pairs(
    rules: list[tuple[int, int, str]] | None,
    vi_in: list[int],
    vo_out: list[int],
    d_way_v: memoryview,
) -> set[tuple[int, int]]:
    """Запрещённые пары (позиция въезда, позиция выезда) вершины-гаджета."""
    if not rules:
        return set()
    in_by_way: dict[int, list[int]] = {}
    for i in vi_in:
        in_by_way.setdefault(d_way_v[i], []).append(i)
    out_by_way: dict[int, list[int]] = {}
    for i in vo_out:
        out_by_way.setdefault(d_way_v[i], []).append(i)
    forbid: set[tuple[int, int]] = set()
    for fw, tw, kind in rules:
        if kind.startswith("only"):
            # only_*: приехав по from_way, выехать можно лишь на to_way.
            # Въезды по другим way ограничение не касается.
            for i in in_by_way.get(fw, []):
                for j in vo_out:
                    if d_way_v[j] != tw:
                        forbid.add((i, j))
        else:
            for i in in_by_way.get(fw, []):
                for j in out_by_way.get(tw, []):
                    forbid.add((i, j))
    return forbid
