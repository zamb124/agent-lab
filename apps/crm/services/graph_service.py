"""
Сервис для работы с графами связей.

Реализует алгоритмы построения графа влияния, поиска кратчайшего пути
и навигации по связям с учетом направленности, весов и прав доступа.

Batch-оптимизация: все операции загружают данные уровнями (wave-front BFS)
или с prefetch (Dijkstra), сводя количество SQL-запросов к O(depth) вместо O(nodes).
"""

from typing import List, Optional, Dict, Any, Tuple, Set
from collections import deque
import heapq
from datetime import datetime, timezone

from apps.crm.db.models import CRMEntity
from apps.crm.models.graph import (
    GraphNode,
    GraphEdge,
    InfluenceGraphResponse,
    ShortestPathResponse,
    RelatedEntitiesResponse
)
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.models import Relationship, RelationshipType
from apps.crm.services.access_control_service import AccessControlService
from core.context import get_context
from core.logging import get_logger

logger = get_logger(__name__)

MAX_NODES_IN_GRAPH = 1000
DIJKSTRA_PREFETCH_BATCH = 30


class GraphEntityLimitExceededError(Exception):
    """Слишком много сущностей в выбранном периоде/пространстве для построения графа."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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
        access_control: AccessControlService
    ):
        self._relationship_repo = relationship_repo
        self._relationship_type_repo = relationship_type_repo
        self._entity_repo = entity_repo
        self._access_control = access_control

    def _timeline_filters_for_count(
        self,
        created_at_from: Optional[datetime],
        created_at_to: Optional[datetime],
    ) -> Optional[Dict[str, Any]]:
        if created_at_from is None and created_at_to is None:
            return None
        created_spec: Dict[str, Any] = {}
        if created_at_from is not None:
            created_spec["$gte"] = created_at_from
        if created_at_to is not None:
            created_spec["$lte"] = created_at_to
        return {"created_at": created_spec}

    async def _ensure_graph_entity_count_within_limit(
        self,
        namespace: Optional[str],
        created_at_from: Optional[datetime],
        created_at_to: Optional[datetime],
    ) -> None:
        if created_at_from is None and created_at_to is None:
            return
        filters = self._timeline_filters_for_count(created_at_from, created_at_to)
        count = await self._entity_repo.count_all(
            namespace=namespace,
            filters=filters,
        )
        if count > MAX_NODES_IN_GRAPH:
            raise GraphEntityLimitExceededError(
                f"В выбранном периоде слишком много сущностей ({count}), "
                f"максимум для графа — {MAX_NODES_IN_GRAPH}. Сузьте период на таймлайне."
            )
    
    def _get_context_info(self) -> Tuple[Optional[str], Optional[str]]:
        ctx = get_context()
        user_id = ctx.user.user_id if ctx and ctx.user else None
        company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
        return user_id, company_id

    @staticmethod
    def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _is_entity_in_time_window(
        self,
        entity: CRMEntity,
        created_at_from: Optional[datetime],
        created_at_to: Optional[datetime],
    ) -> bool:
        if created_at_from is None and created_at_to is None:
            return True
        if entity.created_at is None:
            return False
        entity_created_at = self._normalize_datetime(entity.created_at)
        if created_at_from is not None and entity_created_at < created_at_from:
            return False
        if created_at_to is not None and entity_created_at > created_at_to:
            return False
        return True
    
    async def build_influence_graph(
        self,
        entity_id: str,
        max_depth: int = 3,
        relationship_types: Optional[List[str]] = None,
        created_at_from: Optional[datetime] = None,
        created_at_to: Optional[datetime] = None,
        namespace: Optional[str] = None,
    ) -> InfluenceGraphResponse:
        """
        Строит граф влияния от entity (wave-front BFS).
        
        Каждый уровень обхода — два SQL-запроса (ребра + сущности),
        вместо N+1 запросов на каждый узел.
        """
        user_id, company_id = self._get_context_info()
        timeline_from = self._normalize_datetime(created_at_from)
        timeline_to = self._normalize_datetime(created_at_to)

        await self._ensure_graph_entity_count_within_limit(
            namespace, timeline_from, timeline_to
        )
        
        root_entity = await self._entity_repo.get(entity_id)
        if not root_entity:
            raise ValueError(f"Entity not found: {entity_id}")
        if not self._is_entity_in_time_window(root_entity, timeline_from, timeline_to):
            raise ValueError(f"Root entity is out of created_at range: {entity_id}")
        
        can_read = await self._access_control.can_read_entity(
            root_entity, user_id, company_id
        )
        if not can_read:
            raise PermissionError(f"Access denied to root entity: {entity_id}")
        
        direction_map = await self._build_direction_map()
        
        visited: Set[str] = {entity_id}
        entity_levels: Dict[str, int] = {entity_id: 0}
        entities_dict: Dict[str, CRMEntity] = {entity_id: root_entity}
        edges_dict: Dict[str, Relationship] = {}
        
        current_wave = [entity_id]
        
        for level in range(max_depth):
            if not current_wave:
                break
            if len(visited) > MAX_NODES_IN_GRAPH:
                raise GraphEntityLimitExceededError(
                    f"Граф превышает лимит {MAX_NODES_IN_GRAPH} вершин; сузьте период или глубину."
                )
            
            batch_edges = await self._relationship_repo.get_neighbors(
                current_wave, cross_company=True
            )
            
            candidate_ids: Set[str] = set()
            for current_id in current_wave:
                for rel in batch_edges.get(current_id, []):
                    if relationship_types and rel.relationship_type not in relationship_types:
                        continue
                    
                    can_traverse, neighbor_id = self._can_traverse_edge(
                        rel, current_id, direction_map
                    )
                    if not can_traverse or not neighbor_id:
                        continue
                    
                    if rel.relationship_id not in edges_dict:
                        edges_dict[rel.relationship_id] = rel
                    
                    if neighbor_id not in visited:
                        candidate_ids.add(neighbor_id)
            
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
        filtered_count = sum(1 for node in nodes if not node.access)
        
        logger.info(
            f"Built influence graph: root={entity_id}, depth={max_depth}, "
            f"nodes={len(nodes)}, edges={len(edges)}, filtered={filtered_count}"
        )
        
        return InfluenceGraphResponse(
            root_entity_id=entity_id,
            max_depth=max_depth,
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            filtered_count=filtered_count
        )
    
    async def build_overview_graph(
        self,
        entity_ids: List[str],
        max_depth: int = 3,
        relationship_types: Optional[List[str]] = None,
        created_at_from: Optional[datetime] = None,
        created_at_to: Optional[datetime] = None,
        namespace: Optional[str] = None,
    ) -> InfluenceGraphResponse:
        """Объединённый граф влияния по нескольким seed-сущностям (wave-front BFS)."""
        user_id, company_id = self._get_context_info()
        timeline_from = self._normalize_datetime(created_at_from)
        timeline_to = self._normalize_datetime(created_at_to)

        await self._ensure_graph_entity_count_within_limit(
            namespace, timeline_from, timeline_to
        )

        direction_map = await self._build_direction_map()

        visited: Set[str] = set()
        entity_levels: Dict[str, int] = {}
        entities_dict: Dict[str, CRMEntity] = {}
        edges_dict: Dict[str, Relationship] = {}

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
            if len(visited) > MAX_NODES_IN_GRAPH:
                raise GraphEntityLimitExceededError(
                    f"Граф превышает лимит {MAX_NODES_IN_GRAPH} вершин; сузьте период или глубину."
                )

            batch_edges = await self._relationship_repo.get_neighbors(
                current_wave, cross_company=True
            )

            candidate_ids: Set[str] = set()
            for current_id in current_wave:
                for rel in batch_edges.get(current_id, []):
                    if relationship_types and rel.relationship_type not in relationship_types:
                        continue
                    can_traverse, neighbor_id = self._can_traverse_edge(rel, current_id, direction_map)
                    if not can_traverse or not neighbor_id:
                        continue
                    if rel.relationship_id not in edges_dict:
                        edges_dict[rel.relationship_id] = rel
                    if neighbor_id not in visited:
                        candidate_ids.add(neighbor_id)

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
        filtered_count = sum(1 for node in nodes if not node.access)

        logger.info(
            f"Built overview graph: seeds={len(entity_ids)}, depth={max_depth}, "
            f"nodes={len(nodes)}, edges={len(edges)}, filtered={filtered_count}"
        )

        return InfluenceGraphResponse(
            root_entity_id=entity_ids[0] if entity_ids else '',
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
        created_at_from: Optional[datetime] = None,
        created_at_to: Optional[datetime] = None,
        namespace: Optional[str] = None,
    ) -> ShortestPathResponse:
        """
        Кратчайший путь между entities с учетом весов (Weighted Dijkstra с prefetch).
        """
        user_id, company_id = self._get_context_info()
        timeline_from = self._normalize_datetime(created_at_from)
        timeline_to = self._normalize_datetime(created_at_to)

        await self._ensure_graph_entity_count_within_limit(
            namespace, timeline_from, timeline_to
        )
        
        logger.info(f"Finding shortest path: from={from_entity_id}, to={to_entity_id}, user={user_id}, company={company_id}")
        
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
        
        can_read_from = await self._access_control.can_read_entity(
            from_entity, user_id, company_id
        )
        can_read_to = await self._access_control.can_read_entity(
            to_entity, user_id, company_id
        )
        
        if not can_read_from or not can_read_to:
            raise PermissionError("Access denied to one or both entities")
        
        direction_map = await self._build_direction_map()

        # Общий кэш ребер для обоих прогонов и _build_path_edges
        shared_edges_cache: Dict[str, List[Relationship]] = {}
        
        directed_path, directed_total_distance = await self._dijkstra_shortest_path(
            from_entity_id, to_entity_id, max_depth, direction_map,
            ignore_direction=False,
            created_at_from=timeline_from, created_at_to=timeline_to,
            edges_cache=shared_edges_cache,
        )
        undirected_path, undirected_total_distance = await self._dijkstra_shortest_path(
            from_entity_id, to_entity_id, max_depth, direction_map,
            ignore_direction=True,
            created_at_from=timeline_from, created_at_to=timeline_to,
            edges_cache=shared_edges_cache,
        )

        directed_edges: List[GraphEdge] = []
        if directed_path:
            directed_edges = self._build_path_edges_from_cache(
                directed_path, direction_map, shared_edges_cache, ignore_direction=False
            )
        undirected_edges: List[GraphEdge] = []
        if undirected_path:
            undirected_edges = self._build_path_edges_from_cache(
                undirected_path, direction_map, shared_edges_cache, ignore_direction=True
            )

        logger.info(
            f"Found paths: directed_exists={bool(directed_path)}, undirected_exists={bool(undirected_path)}, "
            f"from={from_entity_id}, to={to_entity_id}"
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
        relationship_type: Optional[str] = None,
        created_at_from: Optional[datetime] = None,
        created_at_to: Optional[datetime] = None,
        namespace: Optional[str] = None,
    ) -> RelatedEntitiesResponse:
        """
        Получает прямо связанные entities (1 уровень).
        Batch-загрузка всех соседей одним запросом.
        """
        user_id, company_id = self._get_context_info()
        timeline_from = self._normalize_datetime(created_at_from)
        timeline_to = self._normalize_datetime(created_at_to)

        await self._ensure_graph_entity_count_within_limit(
            namespace, timeline_from, timeline_to
        )
        
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        if not self._is_entity_in_time_window(entity, timeline_from, timeline_to):
            raise ValueError(f"Entity is out of created_at range: {entity_id}")
        
        direction_map = await self._build_direction_map()
        relationships = await self._relationship_repo.get_by_entity_for_graph(
            entity_id,
            cross_company=True
        )
        
        if relationship_type:
            relationships = [r for r in relationships if r.relationship_type == relationship_type]
        
        incoming_ids: Set[str] = set()
        outgoing_ids: Set[str] = set()
        undirected_ids: Set[str] = set()
        
        for rel in relationships:
            rel_info = direction_map.get(rel.relationship_type)
            if not rel_info:
                logger.warning(f"Unknown relationship_type in get_related_entities: {rel.relationship_type}")
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
        neighbors_dict: Dict[str, CRMEntity] = {}
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
            undirected=undirected_nodes
        )
    
    async def _build_direction_map(self) -> Dict[str, Dict[str, Any]]:
        """Строит карту направленности для быстрого доступа."""
        relationship_types = await self._relationship_type_repo.get_all_for_company(include_system=True)
        
        direction_map = {}
        for rt in relationship_types:
            direction_map[rt.type_id] = {
                "is_directed": rt.is_directed,
                "inverse_type_id": rt.inverse_type_id,
                "weight_default": rt.weight_default
            }
        
        return direction_map
    
    def _can_traverse_edge(
        self,
        relationship: Relationship,
        from_entity_id: str,
        direction_map: Dict[str, Dict[str, Any]],
        ignore_direction: bool = False,
    ) -> Tuple[bool, Optional[str]]:
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
        entities_dict: Dict[str, CRMEntity],
        entity_levels: Dict[str, int],
        user_id: Optional[str],
        company_id: Optional[str],
        *,
        query_namespace: Optional[str] = None,
    ) -> List[GraphNode]:
        """Применяет access control к entities, возвращая placeholder для скрытых."""
        readable = await self._access_control.batch_filter_readable(
            list(entities_dict.values()),
            user_id,
            company_id,
            query_namespace=query_namespace,
        )
        readable_ids: Set[str] = {e.entity_id for e in readable}

        nodes = []
        for entity_id, entity in entities_dict.items():
            level = entity_levels.get(entity_id, 0)

            if entity_id in readable_ids:
                nodes.append(GraphNode(
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    name=entity.name,
                    level=level,
                    access=True,
                    created_at=entity.created_at.isoformat() if entity.created_at else None,
                    attributes=entity.attributes
                ))
            else:
                nodes.append(GraphNode(
                    entity_id=entity.entity_id,
                    entity_type="hidden",
                    name="Hidden",
                    level=level,
                    access=False,
                    created_at=None,
                    attributes=None
                ))

        return nodes
    
    def _build_edges(
        self,
        relationships: List[Relationship],
        direction_map: Dict[str, Dict[str, Any]]
    ) -> List[GraphEdge]:
        """Строит список GraphEdge из relationships."""
        edges = []
        for rel in relationships:
            rel_info = direction_map.get(rel.relationship_type)
            if not rel_info:
                logger.warning(f"Unknown relationship_type in _build_edges: {rel.relationship_type}")
                continue
            
            edges.append(GraphEdge(
                edge_id=rel.relationship_id,
                source_id=rel.source_entity_id,
                target_id=rel.target_entity_id,
                relationship_type=rel.relationship_type,
                weight=rel.weight,
                confidence=rel.confidence,
                is_directed=rel_info["is_directed"],
                attributes=rel.attributes
            ))
        
        return edges
    
    async def _dijkstra_shortest_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int,
        direction_map: Dict[str, Dict[str, Any]],
        ignore_direction: bool = False,
        created_at_from: Optional[datetime] = None,
        created_at_to: Optional[datetime] = None,
        edges_cache: Optional[Dict[str, List[Relationship]]] = None,
    ) -> Tuple[List[str], float]:
        """
        Weighted Dijkstra с prefetch ребер из кэша.
        Кэш разделяется между directed/undirected прогонами и _build_path_edges.
        """
        if from_id == to_id:
            return [from_id], 0.0

        if edges_cache is None:
            edges_cache = {}
        
        distances = {from_id: 0.0}
        parent: Dict[str, str] = {}
        visited: Set[str] = set()
        entities_cache: Dict[str, Optional[CRMEntity]] = {}
        
        heap: list[Tuple[float, str, int]] = [(0.0, from_id, 0)]
        
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
                    list(prefetch_ids), cross_company=True
                )
                edges_cache.update(batch)
            
            relationships = edges_cache.get(current_id, [])
            
            # Batch-загрузка неизвестных соседей
            unknown_neighbors: Set[str] = set()
            traversable: list[Tuple[Relationship, str]] = []
            
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
                if not self._is_entity_in_time_window(neighbor_entity, created_at_from, created_at_to):
                    continue
                
                candidate_distance = current_dist + rel.weight
                
                if neighbor_id not in distances or candidate_distance < distances[neighbor_id]:
                    distances[neighbor_id] = candidate_distance
                    parent[neighbor_id] = current_id
                    heapq.heappush(heap, (candidate_distance, neighbor_id, current_depth + 1))
        
        return [], 0.0
    
    def _reconstruct_path(
        self,
        parent: Dict[str, str],
        from_id: str,
        to_id: str
    ) -> List[str]:
        """Восстанавливает путь из parent map."""
        path = []
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
        path: List[str],
        direction_map: Dict[str, Dict[str, Any]],
        edges_cache: Dict[str, List[Relationship]],
        ignore_direction: bool = False,
    ) -> List[GraphEdge]:
        """Строит edges вдоль пути из кэша ребер (без дополнительных SQL-запросов)."""
        edges = []
        
        for i in range(len(path) - 1):
            source_id = path[i]
            target_id = path[i + 1]
            
            for rel in edges_cache.get(source_id, []):
                can_traverse, neighbor_id = self._can_traverse_edge(
                    rel, source_id, direction_map, ignore_direction=ignore_direction
                )
                
                if can_traverse and neighbor_id == target_id:
                    rel_info = direction_map.get(rel.relationship_type, {})
                    edges.append(GraphEdge(
                        edge_id=rel.relationship_id,
                        source_id=rel.source_entity_id,
                        target_id=rel.target_entity_id,
                        relationship_type=rel.relationship_type,
                        weight=rel.weight,
                        confidence=rel.confidence,
                        is_directed=rel_info.get("is_directed", True),
                        attributes=rel.attributes
                    ))
                    break
        
        return edges
