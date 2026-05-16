"""
Сервис для работы с графами связей.

Реализует алгоритмы построения графа влияния, поиска кратчайшего пути
и навигации по связям с учетом направленности, весов и прав доступа.

Batch-оптимизация: все операции загружают данные уровнями (wave-front BFS)
или с prefetch (Dijkstra), сводя количество SQL-запросов к O(depth) вместо O(nodes).
"""

import heapq
from datetime import UTC, datetime
from typing import TypedDict

from apps.crm.db.models import CRMEntity, Relationship
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.models.graph import (
    GraphEdge,
    GraphNode,
    InfluenceGraphResponse,
    RelatedEntitiesResponse,
    ShortestPathResponse,
)
from apps.crm.services.access_control_service import AccessControlService
from apps.crm.types import JsonObject
from core.context import get_context
from core.logging import get_logger

logger = get_logger(__name__)

MAX_NODES_IN_GRAPH = 1000
"""Жёсткий потолок защиты от ошибок обхода."""
INFLUENCE_GRAPH_MAX_NODES = 200
"""Максимум вершин в ответе influence/overview (обход можно обрезать до этого числа)."""
DIJKSTRA_PREFETCH_BATCH = 30

_TIMELINE_ENTITY_COUNT_FILTER_FIELD_TYPES: dict[str, str] = {"created_at": "datetime"}


class _RelationshipDirectionInfo(TypedDict):
    is_directed: bool
    inverse_type_id: str | None
    weight_default: float


type _RelationshipDirectionMap = dict[str, _RelationshipDirectionInfo]


def _relationship_namespace_for_traversal(
    namespace: str | None,
    include_all_namespaces: bool,
) -> str | None:
    """
    Namespace строки Relationship: при переданном непустом `namespace` обход учитывает
    только рёбра с тем же Relationship.namespace, кроме явного include_all_namespaces.
    """
    if include_all_namespaces:
        return None
    if namespace is None:
        return None
    ns = namespace.strip()
    if len(ns) == 0:
        return None
    return ns


class GraphEntityLimitExceededError(Exception):
    """Слишком много сущностей в выбранном периоде/пространстве для построения графа."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message: str = message


class GraphService:
    """
    Сервис для анализа графа связей.

    Алгоритмы:
    - Wave-front BFS для influence/overview graph (batch per level)
    - Weighted Dijkstra с prefetch для shortest path
    - Учет направленности через is_directed + inverse_type_id
    """

    def __init__(
        self,
        relationship_repo: RelationshipRepository,
        relationship_type_repo: RelationshipTypeRepository,
        entity_repo: EntityRepository,
        access_control: AccessControlService,
    ) -> None:
        self._relationship_repo: RelationshipRepository = relationship_repo
        self._relationship_type_repo: RelationshipTypeRepository = relationship_type_repo
        self._entity_repo: EntityRepository = entity_repo
        self._access_control: AccessControlService = access_control

    def _timeline_filters_for_count(
        self,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
    ) -> JsonObject | None:
        if created_at_from is None and created_at_to is None:
            return None
        leaves: list[JsonObject] = []
        if created_at_from is not None:
            leaves.append({"field": "created_at", "op": "$gte", "value": created_at_from})
        if created_at_to is not None:
            leaves.append({"field": "created_at", "op": "$lte", "value": created_at_to})
        if len(leaves) == 0:
            return None
        if len(leaves) == 1:
            return leaves[0]
        return {"$and": leaves}

    async def _ensure_graph_entity_count_within_limit(
        self,
        namespace: str | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
    ) -> None:
        if created_at_from is None and created_at_to is None:
            return
        filters = self._timeline_filters_for_count(created_at_from, created_at_to)
        count = await self._entity_repo.count_all(
            namespace=namespace,
            filters=filters,
            filter_field_types=_TIMELINE_ENTITY_COUNT_FILTER_FIELD_TYPES,
        )
        if count > MAX_NODES_IN_GRAPH:
            raise GraphEntityLimitExceededError(
                f"В выбранном периоде слишком много сущностей ({count}), "
                + f"максимум для графа — {MAX_NODES_IN_GRAPH}. Сузьте период на таймлайне."
            )

    def _get_context_info(self) -> tuple[str | None, str | None]:
        ctx = get_context()
        user_id = ctx.user.user_id if ctx and ctx.user else None
        company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
        return user_id, company_id

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def _is_entity_in_time_window(
        self,
        entity: CRMEntity,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
    ) -> bool:
        if created_at_from is None and created_at_to is None:
            return True
        entity_created_at = entity.created_at
        if entity_created_at.tzinfo is None:
            entity_created_at = entity_created_at.replace(tzinfo=UTC)
        if created_at_from is not None and entity_created_at < created_at_from:
            return False
        if created_at_to is not None and entity_created_at > created_at_to:
            return False
        return True

    def _cap_influence_candidate_ids(
        self,
        candidate_ids: set[str],
        visited: set[str],
        graph_kind: str,
    ) -> set[str]:
        cap = INFLUENCE_GRAPH_MAX_NODES
        space = cap - len(visited)
        if space <= 0:
            return set()
        if len(candidate_ids) <= space:
            return candidate_ids
        sorted_ids = sorted(candidate_ids)
        truncated = set(sorted_ids[:space])
        logger.warning(
            "%s graph: truncated candidates from %s to %s (visited=%s, cap=%s)",
            graph_kind,
            len(candidate_ids),
            len(truncated),
            len(visited),
            cap,
        )
        return truncated

    async def build_influence_graph(
        self,
        entity_id: str,
        max_depth: int = 3,
        relationship_types: list[str] | None = None,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        namespace: str | None = None,
        include_all_namespaces: bool = False,
    ) -> InfluenceGraphResponse:
        """
        Строит граф влияния от entity (wave-front BFS).

        Каждый уровень обхода — два SQL-запроса (ребра + сущности),
        вместо N+1 запросов на каждый узел.

        При непустом query ``namespace`` в рёбрах обхода участвуют только связи с тем же
        ``Relationship.namespace``, если ``include_all_namespaces`` не задан.
        """
        user_id, company_id = self._get_context_info()
        timeline_from = self._normalize_datetime(created_at_from)
        timeline_to = self._normalize_datetime(created_at_to)
        rel_namespace = _relationship_namespace_for_traversal(namespace, include_all_namespaces)

        await self._ensure_graph_entity_count_within_limit(namespace, timeline_from, timeline_to)

        root_entity = await self._entity_repo.get(entity_id)
        if not root_entity:
            raise ValueError(f"Entity not found: {entity_id}")
        # Фильтр периода задаёт обход соседей; корневая сущность всегда остаётся в графе.

        can_read = await self._access_control.can_read_entity(root_entity, user_id, company_id)
        if not can_read:
            raise PermissionError(f"Access denied to root entity: {entity_id}")

        direction_map = await self._build_direction_map()

        visited: set[str] = {entity_id}
        entity_levels: dict[str, int] = {entity_id: 0}
        entities_dict: dict[str, CRMEntity] = {entity_id: root_entity}
        edges_dict: dict[str, Relationship] = {}

        current_wave = [entity_id]

        for level in range(max_depth):
            if not current_wave:
                break
            if len(visited) >= INFLUENCE_GRAPH_MAX_NODES:
                logger.warning(
                    "influence graph: expansion stopped at visited=%s (cap=%s)",
                    len(visited),
                    INFLUENCE_GRAPH_MAX_NODES,
                )
                break

            batch_edges = await self._relationship_repo.get_neighbors(
                current_wave,
                cross_company=True,
                relationship_namespace=rel_namespace,
            )

            candidate_ids: set[str] = set()
            for current_id in current_wave:
                for rel in batch_edges.get(current_id, []):
                    if relationship_types and rel.relationship_type not in relationship_types:
                        continue

                    can_traverse, neighbor_id = self._can_traverse_edge(
                        rel, current_id, direction_map, ignore_direction=False
                    )
                    if not can_traverse or not neighbor_id:
                        continue

                    if rel.relationship_id not in edges_dict:
                        edges_dict[rel.relationship_id] = rel

                    if neighbor_id not in visited:
                        candidate_ids.add(neighbor_id)

            if not candidate_ids:
                break

            candidate_ids = self._cap_influence_candidate_ids(candidate_ids, visited, "influence")
            if not candidate_ids:
                break

            loaded_entities = await self._entity_repo.get_by_ids(list(candidate_ids))
            entities_by_id = {e.entity_id: e for e in loaded_entities}

            next_wave: list[str] = []
            for neighbor_id in candidate_ids:
                neighbor = entities_by_id.get(neighbor_id)
                if not neighbor:
                    continue
                if not self._is_entity_in_time_window(neighbor, timeline_from, timeline_to):
                    continue
                visited.add(neighbor_id)
                entity_levels[neighbor_id] = level + 1
                entities_dict[neighbor_id] = neighbor
                next_wave.append(neighbor_id)

            current_wave = next_wave

        nodes = await self._apply_access_control(
            entities_dict,
            entity_levels,
            user_id,
            company_id,
            query_namespace=namespace,
        )
        edges = self._build_edges(list(edges_dict.values()), direction_map)
        nodes, edges = self._finalize_graph_payload(nodes, edges, "influence graph")
        filtered_count = sum(1 for node in nodes if not node.access)

        logger.info(
            "Built influence graph: root=%s, depth=%s, nodes=%s, edges=%s, filtered=%s",
            entity_id,
            max_depth,
            len(nodes),
            len(edges),
            filtered_count,
        )

        return InfluenceGraphResponse(
            root_entity_id=entity_id,
            max_depth=max_depth,
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            filtered_count=filtered_count,
        )

    async def build_overview_graph(
        self,
        entity_ids: list[str],
        max_depth: int = 3,
        relationship_types: list[str] | None = None,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        namespace: str | None = None,
        include_all_namespaces: bool = False,
    ) -> InfluenceGraphResponse:
        """Объединённый граф влияния по нескольким seed-сущностям (wave-front BFS).

        При непустом query ``namespace`` в рёбрах обхода участвуют только связи с тем же
        ``Relationship.namespace``, если ``include_all_namespaces`` не задан.
        """
        user_id, company_id = self._get_context_info()
        timeline_from = self._normalize_datetime(created_at_from)
        timeline_to = self._normalize_datetime(created_at_to)
        rel_namespace = _relationship_namespace_for_traversal(namespace, include_all_namespaces)

        await self._ensure_graph_entity_count_within_limit(namespace, timeline_from, timeline_to)

        direction_map = await self._build_direction_map()

        visited: set[str] = set()
        entity_levels: dict[str, int] = {}
        entities_dict: dict[str, CRMEntity] = {}
        edges_dict: dict[str, Relationship] = {}

        seed_entities = await self._entity_repo.get_by_ids(entity_ids)
        readable_seeds = await self._access_control.batch_filter_readable(
            seed_entities,
            user_id,
            company_id,
            query_namespace=namespace,
        )
        readable_seeds_by_id = {e.entity_id: e for e in readable_seeds}

        initial_wave: list[str] = []
        for seed_id in entity_ids:
            if len(visited) >= INFLUENCE_GRAPH_MAX_NODES:
                logger.warning(
                    "overview graph: seed list truncated at cap=%s",
                    INFLUENCE_GRAPH_MAX_NODES,
                )
                break
            if seed_id in visited:
                continue
            seed_entity = readable_seeds_by_id.get(seed_id)
            if not seed_entity:
                continue
            if not self._is_entity_in_time_window(seed_entity, timeline_from, timeline_to):
                continue
            visited.add(seed_id)
            entity_levels[seed_id] = 0
            entities_dict[seed_id] = seed_entity
            initial_wave.append(seed_id)

        current_wave = initial_wave

        for level in range(max_depth):
            if not current_wave:
                break
            if len(visited) >= INFLUENCE_GRAPH_MAX_NODES:
                logger.warning(
                    "overview graph: expansion stopped at visited=%s (cap=%s)",
                    len(visited),
                    INFLUENCE_GRAPH_MAX_NODES,
                )
                break

            batch_edges = await self._relationship_repo.get_neighbors(
                current_wave,
                cross_company=True,
                relationship_namespace=rel_namespace,
            )

            candidate_ids: set[str] = set()
            for current_id in current_wave:
                for rel in batch_edges.get(current_id, []):
                    if relationship_types and rel.relationship_type not in relationship_types:
                        continue
                    can_traverse, neighbor_id = self._can_traverse_edge(
                        rel, current_id, direction_map, ignore_direction=False
                    )
                    if not can_traverse or not neighbor_id:
                        continue
                    if rel.relationship_id not in edges_dict:
                        edges_dict[rel.relationship_id] = rel
                    if neighbor_id not in visited:
                        candidate_ids.add(neighbor_id)

            if not candidate_ids:
                break

            candidate_ids = self._cap_influence_candidate_ids(candidate_ids, visited, "overview")
            if not candidate_ids:
                break

            loaded_entities = await self._entity_repo.get_by_ids(list(candidate_ids))
            entities_by_id = {e.entity_id: e for e in loaded_entities}

            next_wave: list[str] = []
            for neighbor_id in candidate_ids:
                neighbor = entities_by_id.get(neighbor_id)
                if not neighbor:
                    continue
                if not self._is_entity_in_time_window(neighbor, timeline_from, timeline_to):
                    continue
                visited.add(neighbor_id)
                entity_levels[neighbor_id] = level + 1
                entities_dict[neighbor_id] = neighbor
                next_wave.append(neighbor_id)

            current_wave = next_wave

            if len(visited) > MAX_NODES_IN_GRAPH:
                raise GraphEntityLimitExceededError(
                    f"Граф превышает лимит {MAX_NODES_IN_GRAPH} вершин; сузьте период или глубину."
                )

        nodes = await self._apply_access_control(
            entities_dict,
            entity_levels,
            user_id,
            company_id,
            query_namespace=namespace,
        )
        edges = self._build_edges(list(edges_dict.values()), direction_map)
        nodes, edges = self._finalize_graph_payload(nodes, edges, "overview graph")
        filtered_count = sum(1 for node in nodes if not node.access)

        logger.info(
            "Built overview graph: seeds=%s, depth=%s, nodes=%s, edges=%s, filtered=%s",
            len(entity_ids),
            max_depth,
            len(nodes),
            len(edges),
            filtered_count,
        )

        return InfluenceGraphResponse(
            root_entity_id=entity_ids[0] if entity_ids else "",
            max_depth=max_depth,
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            filtered_count=filtered_count,
        )

    async def find_shortest_path(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 10,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        namespace: str | None = None,
        include_all_namespaces: bool = False,
    ) -> ShortestPathResponse:
        """
        Кратчайший путь между entities с учетом весов (Weighted Dijkstra с prefetch).

        При непустом query ``namespace`` обход учитывает только связи с тем же
        ``Relationship.namespace``, если ``include_all_namespaces`` не задан.
        """
        user_id, company_id = self._get_context_info()
        timeline_from = self._normalize_datetime(created_at_from)
        timeline_to = self._normalize_datetime(created_at_to)
        rel_namespace = _relationship_namespace_for_traversal(namespace, include_all_namespaces)

        await self._ensure_graph_entity_count_within_limit(namespace, timeline_from, timeline_to)

        logger.info(
            f"Finding shortest path: from={from_entity_id}, to={to_entity_id}, user={user_id}, company={company_id}"
        )

        from_entity = await self._entity_repo.get(from_entity_id)
        to_entity = await self._entity_repo.get(to_entity_id)

        if not from_entity:
            raise ValueError(f"Entity not found: {from_entity_id}")
        if not to_entity:
            raise ValueError(f"Entity not found: {to_entity_id}")
        if not self._is_entity_in_time_window(from_entity, timeline_from, timeline_to):
            raise ValueError(f"From entity is out of created_at range: {from_entity_id}")
        if not self._is_entity_in_time_window(to_entity, timeline_from, timeline_to):
            raise ValueError(f"To entity is out of created_at range: {to_entity_id}")

        can_read_from = await self._access_control.can_read_entity(from_entity, user_id, company_id)
        can_read_to = await self._access_control.can_read_entity(to_entity, user_id, company_id)

        if not can_read_from or not can_read_to:
            raise PermissionError("Access denied to one or both entities")

        direction_map = await self._build_direction_map()

        # Общий кэш ребер для обоих прогонов и _build_path_edges
        shared_edges_cache: dict[str, list[Relationship]] = {}

        directed_path, directed_total_distance = await self._dijkstra_shortest_path(
            from_entity_id,
            to_entity_id,
            max_depth,
            direction_map,
            ignore_direction=False,
            created_at_from=timeline_from,
            created_at_to=timeline_to,
            edges_cache=shared_edges_cache,
            relationship_namespace=rel_namespace,
        )
        undirected_path, undirected_total_distance = await self._dijkstra_shortest_path(
            from_entity_id,
            to_entity_id,
            max_depth,
            direction_map,
            ignore_direction=True,
            created_at_from=timeline_from,
            created_at_to=timeline_to,
            edges_cache=shared_edges_cache,
            relationship_namespace=rel_namespace,
        )

        directed_edges: list[GraphEdge] = []
        if directed_path:
            directed_edges = self._build_path_edges_from_cache(
                directed_path, direction_map, shared_edges_cache, ignore_direction=False
            )
        undirected_edges: list[GraphEdge] = []
        if undirected_path:
            undirected_edges = self._build_path_edges_from_cache(
                undirected_path, direction_map, shared_edges_cache, ignore_direction=True
            )

        logger.info(
            "Found paths: directed_exists=%s, undirected_exists=%s, from=%s, to=%s",
            bool(directed_path),
            bool(undirected_path),
            from_entity_id,
            to_entity_id,
        )

        return ShortestPathResponse(
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            path=directed_path,
            edges=directed_edges,
            total_distance=directed_total_distance,
            exists=len(directed_path) > 0,
            undirected_path=undirected_path,
            undirected_edges=undirected_edges,
            undirected_total_distance=undirected_total_distance,
            undirected_exists=len(undirected_path) > 0,
        )

    async def get_related_entities(
        self,
        entity_id: str,
        direction: str = "both",
        relationship_type: str | None = None,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        namespace: str | None = None,
        include_all_namespaces: bool = False,
    ) -> RelatedEntitiesResponse:
        """
        Получает прямо связанные entities (1 уровень).
        Batch-загрузка всех соседей одним запросом.

        При непустом query ``namespace`` учитываются только связи с тем же
        ``Relationship.namespace``, если ``include_all_namespaces`` не задан.
        """
        user_id, company_id = self._get_context_info()
        timeline_from = self._normalize_datetime(created_at_from)
        timeline_to = self._normalize_datetime(created_at_to)
        rel_namespace = _relationship_namespace_for_traversal(namespace, include_all_namespaces)

        await self._ensure_graph_entity_count_within_limit(namespace, timeline_from, timeline_to)

        if (await self._entity_repo.get(entity_id)) is None:
            raise ValueError(f"Entity not found: {entity_id}")

        direction_map = await self._build_direction_map()
        relationships = await self._relationship_repo.get_by_entity_for_graph(
            entity_id,
            cross_company=True,
            relationship_namespace=rel_namespace,
        )

        if relationship_type:
            relationships = [r for r in relationships if r.relationship_type == relationship_type]

        incoming_ids: set[str] = set()
        outgoing_ids: set[str] = set()
        undirected_ids: set[str] = set()

        for rel in relationships:
            rel_info = direction_map.get(rel.relationship_type)
            if not rel_info:
                logger.warning(
                    f"Unknown relationship_type in get_related_entities: {rel.relationship_type}"
                )
                continue
            is_directed = rel_info["is_directed"]

            if rel.source_entity_id == entity_id:
                if is_directed:
                    outgoing_ids.add(rel.target_entity_id)
                else:
                    undirected_ids.add(rel.target_entity_id)

            if rel.target_entity_id == entity_id:
                if is_directed:
                    incoming_ids.add(rel.source_entity_id)
                else:
                    undirected_ids.add(rel.source_entity_id)

        all_neighbor_ids = incoming_ids | outgoing_ids | undirected_ids

        loaded_entities = await self._entity_repo.get_by_ids(list(all_neighbor_ids))
        neighbors_dict: dict[str, CRMEntity] = {}
        for neighbor in loaded_entities:
            if self._is_entity_in_time_window(neighbor, timeline_from, timeline_to):
                neighbors_dict[neighbor.entity_id] = neighbor

        entity_levels = {eid: 1 for eid in neighbors_dict}

        all_nodes = await self._apply_access_control(
            neighbors_dict,
            entity_levels,
            user_id,
            company_id,
            query_namespace=namespace,
        )

        nodes_by_id = {node.entity_id: node for node in all_nodes}

        if direction == "incoming":
            incoming_nodes = [nodes_by_id[eid] for eid in incoming_ids if eid in nodes_by_id]
            outgoing_nodes = []
        elif direction == "outgoing":
            incoming_nodes = []
            outgoing_nodes = [nodes_by_id[eid] for eid in outgoing_ids if eid in nodes_by_id]
        else:
            incoming_nodes = [nodes_by_id[eid] for eid in incoming_ids if eid in nodes_by_id]
            outgoing_nodes = [nodes_by_id[eid] for eid in outgoing_ids if eid in nodes_by_id]

        undirected_nodes = [nodes_by_id[eid] for eid in undirected_ids if eid in nodes_by_id]

        return RelatedEntitiesResponse(
            entity_id=entity_id,
            incoming=incoming_nodes,
            outgoing=outgoing_nodes,
            undirected=undirected_nodes,
        )

    async def _build_direction_map(self) -> _RelationshipDirectionMap:
        """Строит карту направленности для быстрого доступа."""
        relationship_types = await self._relationship_type_repo.get_all_for_company(
            include_system=True
        )

        direction_map: _RelationshipDirectionMap = {}
        for rt in relationship_types:
            direction_map[rt.type_id] = {
                "is_directed": rt.is_directed,
                "inverse_type_id": rt.inverse_type_id,
                "weight_default": rt.weight_default,
            }

        return direction_map

    def _can_traverse_edge(
        self,
        relationship: Relationship,
        from_entity_id: str,
        direction_map: _RelationshipDirectionMap,
        ignore_direction: bool = False,
    ) -> tuple[bool, str | None]:
        """Проверяет можно ли пройти ребро от from_entity_id."""
        rel_info = direction_map.get(relationship.relationship_type)
        if not rel_info:
            logger.warning(f"Unknown relationship_type: {relationship.relationship_type}")
            return False, None

        is_directed = rel_info["is_directed"]
        inverse_type_id = rel_info.get("inverse_type_id")

        if relationship.source_entity_id == from_entity_id:
            return True, relationship.target_entity_id

        if relationship.target_entity_id == from_entity_id:
            if ignore_direction:
                return True, relationship.source_entity_id
            if not is_directed:
                return True, relationship.source_entity_id
            elif inverse_type_id:
                return True, relationship.source_entity_id
            else:
                return False, None

        return False, None

    async def _apply_access_control(
        self,
        entities_dict: dict[str, CRMEntity],
        entity_levels: dict[str, int],
        user_id: str | None,
        company_id: str | None,
        *,
        query_namespace: str | None = None,
    ) -> list[GraphNode]:
        """Применяет access control к entities, возвращая placeholder для скрытых."""
        readable = await self._access_control.batch_filter_readable(
            list(entities_dict.values()),
            user_id,
            company_id,
            query_namespace=query_namespace,
        )
        readable_ids: set[str] = {e.entity_id for e in readable}

        nodes: list[GraphNode] = []
        for entity_id, entity in entities_dict.items():
            level = entity_levels.get(entity_id, 0)

            if entity_id in readable_ids:
                nodes.append(
                    GraphNode(
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        name=entity.name,
                        level=level,
                        access=True,
                        created_at=entity.created_at.isoformat() if entity.created_at else None,
                        attributes=entity.attributes,
                    )
                )
            else:
                nodes.append(
                    GraphNode(
                        entity_id=entity.entity_id,
                        entity_type="hidden",
                        name="Hidden",
                        level=level,
                        access=False,
                        created_at=None,
                        attributes=None,
                    )
                )

        return nodes

    def _build_edges(
        self,
        relationships: list[Relationship],
        direction_map: _RelationshipDirectionMap,
    ) -> list[GraphEdge]:
        """Строит список GraphEdge из relationships."""
        edges: list[GraphEdge] = []
        for rel in relationships:
            rel_info = direction_map.get(rel.relationship_type)
            if not rel_info:
                logger.warning(
                    f"Unknown relationship_type in _build_edges: {rel.relationship_type}"
                )
                continue

            edges.append(
                GraphEdge(
                    edge_id=rel.relationship_id,
                    source_id=rel.source_entity_id,
                    target_id=rel.target_entity_id,
                    relationship_type=rel.relationship_type,
                    weight=rel.weight,
                    confidence=rel.confidence,
                    is_directed=rel_info["is_directed"],
                    attributes=rel.attributes,
                )
            )

        return edges

    def _filter_edges_to_nodes(
        self,
        edges: list[GraphEdge],
        nodes: list[GraphNode],
    ) -> list[GraphEdge]:
        """Оставляет только рёбра, оба конца которых есть в итоговом списке узлов."""
        node_ids = {n.entity_id for n in nodes}
        return [e for e in edges if e.source_id in node_ids and e.target_id in node_ids]

    def _dedupe_graph_nodes_min_level(self, nodes: list[GraphNode]) -> tuple[list[GraphNode], int]:
        best_by_id: dict[str, GraphNode] = {}
        for n in nodes:
            prev = best_by_id.get(n.entity_id)
            if prev is None:
                best_by_id[n.entity_id] = n
                continue
            if n.level < prev.level:
                best_by_id[n.entity_id] = n
        merged = sorted(best_by_id.values(), key=lambda x: x.entity_id)
        return merged, len(nodes) - len(merged)

    def _dedupe_graph_edges_by_edge_id(self, edges: list[GraphEdge]) -> tuple[list[GraphEdge], int]:
        by_id: dict[str, GraphEdge] = {}
        for e in edges:
            by_id[e.edge_id] = e
        merged = sorted(by_id.values(), key=lambda x: x.edge_id)
        return merged, len(edges) - len(merged)

    def _finalize_graph_payload(
        self,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        log_prefix: str,
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        edges = self._filter_edges_to_nodes(edges, nodes)
        nodes, dup_node_rows = self._dedupe_graph_nodes_min_level(nodes)
        if dup_node_rows > 0:
            logger.warning(
                "%s: merged %s duplicate GraphNode rows (same entity_id), minimal level kept",
                log_prefix,
                dup_node_rows,
            )
            edges = self._filter_edges_to_nodes(edges, nodes)
        edges, dup_edge_rows = self._dedupe_graph_edges_by_edge_id(edges)
        if dup_edge_rows > 0:
            logger.warning(
                "%s: dropped %s duplicate GraphEdge rows (same edge_id)",
                log_prefix,
                dup_edge_rows,
            )
        return nodes, edges

    async def _dijkstra_shortest_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int,
        direction_map: _RelationshipDirectionMap,
        ignore_direction: bool = False,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        edges_cache: dict[str, list[Relationship]] | None = None,
        relationship_namespace: str | None = None,
    ) -> tuple[list[str], float]:
        """
        Weighted Dijkstra с prefetch ребер из кэша.
        Кэш разделяется между directed/undirected прогонами и _build_path_edges.
        """
        if from_id == to_id:
            return [from_id], 0.0

        if edges_cache is None:
            edges_cache = {}

        distances = {from_id: 0.0}
        parent: dict[str, str] = {}
        visited: set[str] = set()
        entities_cache: dict[str, CRMEntity | None] = {}

        heap: list[tuple[float, str, int]] = [(0.0, from_id, 0)]

        while heap:
            current_dist, current_id, current_depth = heapq.heappop(heap)

            if current_id in visited:
                continue

            visited.add(current_id)

            if current_id == to_id:
                path = self._reconstruct_path(parent, from_id, to_id)
                return path, current_dist

            if current_depth >= max_depth:
                continue

            # Prefetch: загрузить ребра текущей вершины + ближайших из кучи
            if current_id not in edges_cache:
                prefetch_ids = {current_id}
                for _, nid, _ in heap:
                    if nid not in edges_cache and nid not in visited:
                        prefetch_ids.add(nid)
                        if len(prefetch_ids) >= DIJKSTRA_PREFETCH_BATCH:
                            break
                batch = await self._relationship_repo.get_neighbors(
                    list(prefetch_ids),
                    cross_company=True,
                    relationship_namespace=relationship_namespace,
                )
                edges_cache.update(batch)

            relationships = edges_cache.get(current_id, [])

            # Batch-загрузка неизвестных соседей
            unknown_neighbors: set[str] = set()
            traversable: list[tuple[Relationship, str]] = []

            for rel in relationships:
                can_traverse, neighbor_id = self._can_traverse_edge(
                    rel, current_id, direction_map, ignore_direction=ignore_direction
                )
                if not can_traverse or not neighbor_id or neighbor_id in visited:
                    continue
                traversable.append((rel, neighbor_id))
                if neighbor_id not in entities_cache:
                    unknown_neighbors.add(neighbor_id)

            if unknown_neighbors:
                loaded = await self._entity_repo.get_by_ids(list(unknown_neighbors))
                for e in loaded:
                    entities_cache[e.entity_id] = e
                for nid in unknown_neighbors:
                    if nid not in entities_cache:
                        entities_cache[nid] = None

            for rel, neighbor_id in traversable:
                neighbor_entity = entities_cache.get(neighbor_id)
                if not neighbor_entity:
                    continue
                if not self._is_entity_in_time_window(
                    neighbor_entity, created_at_from, created_at_to
                ):
                    continue

                candidate_distance = current_dist + rel.weight

                if neighbor_id not in distances or candidate_distance < distances[neighbor_id]:
                    distances[neighbor_id] = candidate_distance
                    parent[neighbor_id] = current_id
                    heapq.heappush(heap, (candidate_distance, neighbor_id, current_depth + 1))

        return [], 0.0

    def _reconstruct_path(
        self,
        parent: dict[str, str],
        from_id: str,
        to_id: str,
    ) -> list[str]:
        """Восстанавливает путь из parent map."""
        path: list[str] = []
        current = to_id

        while current != from_id:
            path.append(current)
            if current not in parent:
                return []
            current = parent[current]

        path.append(from_id)
        path.reverse()

        return path

    def _build_path_edges_from_cache(
        self,
        path: list[str],
        direction_map: _RelationshipDirectionMap,
        edges_cache: dict[str, list[Relationship]],
        ignore_direction: bool = False,
    ) -> list[GraphEdge]:
        """Строит edges вдоль пути из кэша ребер (без дополнительных SQL-запросов)."""
        edges: list[GraphEdge] = []

        for i in range(len(path) - 1):
            source_id = path[i]
            target_id = path[i + 1]

            for rel in edges_cache.get(source_id, []):
                can_traverse, neighbor_id = self._can_traverse_edge(
                    rel, source_id, direction_map, ignore_direction=ignore_direction
                )

                if can_traverse and neighbor_id == target_id:
                    rel_info = direction_map.get(rel.relationship_type)
                    if rel_info is None:
                        raise ValueError(
                            f"Unknown relationship_type in path: {rel.relationship_type}"
                        )
                    edges.append(
                        GraphEdge(
                            edge_id=rel.relationship_id,
                            source_id=rel.source_entity_id,
                            target_id=rel.target_entity_id,
                            relationship_type=rel.relationship_type,
                            weight=rel.weight,
                            confidence=rel.confidence,
                            is_directed=rel_info["is_directed"],
                            attributes=rel.attributes,
                        )
                    )
                    break

        return edges
