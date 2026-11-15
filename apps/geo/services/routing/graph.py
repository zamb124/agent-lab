"""CSR-граф режима маршрута одного поколения импорта.

Postgres (`geo_road_edges` и оверлеи) — source of truth; ``ModeGraphs`` —
производное read-only представление, которое SQL-роутинг материализовал на
каждый запрос (~800MB IO). Граф собирается один раз на поколение: scipy
``dijkstra`` по нему — десятки миллисекунд вместо секунд.

Две топологии на режим — семантика существующих контрактов разная:

- ``plain`` — чистый нода-граф: ``matrix``/``isochrone``/``optimal_order``
  идут dijkstra без учёта рестрикций (историческая семантика контрактов);
- ``full`` — нода-граф + edge-state gadgets: вершины с запретами поворотов,
  барьерами и светофорами разворачиваются в полуузлы ``vin``/``vout``,
  переходы между которыми несут штраф (запрет = ``1e12``, как в TRSP).
  ``route/calculate`` = TRSP-паритет.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.sparse import csr_matrix

# Штраф запрещённого перехода — паритет ``_FORBIDDEN`` TRSP: объезд
# выбирается всегда, но без объезда маршрут всё же находится.
FORBIDDEN = 1e12


@dataclass(frozen=True, slots=True)
class CsrGraph:
    """Направленный взвешенный граф + происхождение каждой дуги.

    ``indptr``/``indices`` — те же буферы, что хранит ``csr``
    (``copy=False``); поля дублируют ссылку ради типизированного доступа:
    атрибуты ``csr_matrix`` в стабах возвращают ``Any``.
    """

    csr: csr_matrix
    indptr: npt.NDArray[np.int32]  # [n_nodes + 1]
    indices: npt.NDArray[np.int32]  # [nnz]
    # id ребра ``geo_road_edges`` на позицию дуги; -1 — gadget-переход
    # (не физическое ребро, в геометрию пути не попадает).
    edge_id: npt.NDArray[np.int64]  # [nnz]
    # Дуга едет против ориентации ребра (target→source по ``reverse_cost``).
    backward: npt.NDArray[np.bool_]  # [nnz]


@dataclass(frozen=True, slots=True)
class ModeGraphs:
    """Пара графов режима маршрута на одно поколение."""

    mode: str
    generation: int
    # Отсортированные ``node_id`` базовых вершин; индекс = base-вершина CSR.
    # ``np.searchsorted(vertex_ids, node_id)`` — маппинг без dict.
    vertex_ids: npt.NDArray[np.int64]  # [n_base]
    n_base: int
    plain_time: CsrGraph
    plain_dist: CsrGraph
    full_time: CsrGraph
    n_nodes: int
    # Привязка концов ребра в gadget-графе: (base_vidx, edge_id) → узел.
    # ``arr`` — «приехал в вершину по этому ребру», ``dep`` — «стою в
    # вершине, выезжаю по этому ребру». Вершина без gadget — её base-индекс.
    arr_node: dict[tuple[int, int], int]
    dep_node: dict[tuple[int, int], int]

    def arrival(self, base_vidx: int, edge_id: int) -> int:
        return self.arr_node.get((base_vidx, edge_id), base_vidx)

    def departure(self, base_vidx: int, edge_id: int) -> int:
        return self.dep_node.get((base_vidx, edge_id), base_vidx)


def edge_at(g: CsrGraph, u: int, v: int) -> tuple[int, bool]:
    """id ребра и направление дуги ``u→v``; ``(-1, False)`` для перехода.

    ``memoryview`` — типизированный zero-copy доступ к буферам: скалярная
    индексация ``ndarray`` в стабах возвращает ``Any``.
    """
    indptr = memoryview(g.indptr)
    indices = memoryview(g.indices)
    edge_ids = memoryview(g.edge_id)
    backward = memoryview(g.backward)
    for k in range(indptr[u], indptr[u + 1]):
        if indices[k] == v:
            return edge_ids[k], backward[k] != 0
    return -1, False
