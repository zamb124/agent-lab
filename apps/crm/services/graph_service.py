"""
Сервис для работы с графами связей.

Реализует алгоритмы построения графа влияния, поиска кратчайшего пути
и навигации по связям с учетом направленности, весов и прав доступа.
"""

from typing import List, Optional, Dict, Any, Tuple, Set
from collections import deque
import heapq

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


class GraphService:
    """
    Сервис для анализа графа связей.
    
    Алгоритмы:
    - BFS для influence graph
    - Bidirectional Weighted Dijkstra для shortest path
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
    
    def _get_context_info(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Получить user_id и company_id из контекста.
        
        Returns:
            (user_id, company_id)
        """
        ctx = get_context()
        user_id = ctx.user.user_id if ctx and ctx.user else None
        company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
        return user_id, company_id
    
    async def build_influence_graph(
        self,
        entity_id: str,
        max_depth: int = 3,
        relationship_types: Optional[List[str]] = None
    ) -> InfluenceGraphResponse:
        """
        Строит граф влияния от entity с учетом:
        - Направленности связей (is_directed + inverse_type_id)
        - Прав доступа (placeholder если нет доступа)
        - Типов связей (фильтр по relationship_types)
        
        Args:
            entity_id: Корневая entity
            max_depth: Максимальная глубина обхода (1-5)
            relationship_types: Фильтр по типам связей
        
        Returns:
            InfluenceGraphResponse с nodes и edges
        
        Raises:
            ValueError: Если entity не найдена
            PermissionError: Если нет доступа к корневой entity
        """
        user_id, company_id = self._get_context_info()
        
        root_entity = await self._entity_repo.get(entity_id)
        if not root_entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        can_read = await self._access_control.can_read_entity(
            root_entity, user_id, company_id
        )
        if not can_read:
            raise PermissionError(f"Access denied to root entity: {entity_id}")
        
        direction_map = await self._build_direction_map()
        
        visited: Set[str] = set()
        entity_levels: Dict[str, int] = {entity_id: 0}
        entities_dict: Dict[str, CRMEntity] = {entity_id: root_entity}
        edges_dict: Dict[str, Relationship] = {}  # Используем dict для дедупликации по relationship_id
        
        queue = deque([(entity_id, 0)])
        visited.add(entity_id)
        
        while queue:
            if len(visited) > MAX_NODES_IN_GRAPH:
                logger.warning(f"Graph too large, stopping at {MAX_NODES_IN_GRAPH} nodes")
                break
            
            current_id, current_level = queue.popleft()
            
            if current_level >= max_depth:
                continue
            
            relationships = await self._relationship_repo.get_by_entity_for_graph(
                current_id,
                cross_company=True
            )
            
            for rel in relationships:
                if relationship_types and rel.relationship_type not in relationship_types:
                    continue
                
                can_traverse, neighbor_id = self._can_traverse_edge(
                    rel, current_id, direction_map
                )
                
                if not can_traverse or not neighbor_id:
                    continue
                
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    entity_levels[neighbor_id] = current_level + 1
                    queue.append((neighbor_id, current_level + 1))
                    
                    neighbor_entity = await self._entity_repo.get(neighbor_id)
                    if neighbor_entity:
                        entities_dict[neighbor_id] = neighbor_entity
                
                # Добавляем ребро только раз (по relationship_id)
                if rel.relationship_id not in edges_dict:
                    edges_dict[rel.relationship_id] = rel
        
        nodes = await self._apply_access_control(
            entities_dict, entity_levels, user_id, company_id
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
    
    async def find_shortest_path(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 10
    ) -> ShortestPathResponse:
        """
        Кратчайший путь между entities с учетом весов.
        
        Использует Bidirectional Weighted Dijkstra для оптимизации.
        
        Args:
            from_entity_id: Начальная entity
            to_entity_id: Конечная entity
            max_depth: Максимальная глубина поиска
        
        Returns:
            ShortestPathResponse с path и edges
        """
        user_id, company_id = self._get_context_info()
        
        logger.info(f"Finding shortest path: from={from_entity_id}, to={to_entity_id}, user={user_id}, company={company_id}")
        
        from_entity = await self._entity_repo.get(from_entity_id)
        to_entity = await self._entity_repo.get(to_entity_id)
        
        if not from_entity:
            logger.error(f"From entity not found: {from_entity_id}")
            raise ValueError(f"Entity not found: {from_entity_id}")
        if not to_entity:
            logger.error(f"To entity not found: {to_entity_id}")
            raise ValueError(f"Entity not found: {to_entity_id}")
        
        can_read_from = await self._access_control.can_read_entity(
            from_entity, user_id, company_id
        )
        can_read_to = await self._access_control.can_read_entity(
            to_entity, user_id, company_id
        )
        
        if not can_read_from or not can_read_to:
            raise PermissionError("Access denied to one or both entities")
        
        direction_map = await self._build_direction_map()
        
        path, total_distance = await self._dijkstra_shortest_path(
            from_entity_id, to_entity_id, max_depth, direction_map
        )
        
        if not path:
            return ShortestPathResponse(
                from_entity_id=from_entity_id,
                to_entity_id=to_entity_id,
                path=[],
                edges=[],
                total_distance=0.0,
                exists=False
            )
        
        edges = await self._build_path_edges(path, direction_map)
        
        logger.info(
            f"Found shortest path: {from_entity_id} -> {to_entity_id}, "
            f"length={len(path)}, distance={total_distance}"
        )
        
        return ShortestPathResponse(
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            path=path,
            edges=edges,
            total_distance=total_distance,
            exists=True
        )
    
    async def get_related_entities(
        self,
        entity_id: str,
        direction: str = "both",
        relationship_type: Optional[str] = None
    ) -> RelatedEntitiesResponse:
        """
        Получает прямо связанные entities (1 уровень).
        
        Args:
            entity_id: ID центральной entity
            direction: "incoming" | "outgoing" | "both"
            relationship_type: Фильтр по типу связи
        
        Returns:
            RelatedEntitiesResponse с incoming, outgoing, undirected
        """
        user_id, company_id = self._get_context_info()
        
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
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
            rel_info = direction_map.get(rel.relationship_type, {})
            is_directed = rel_info.get("is_directed", True)
            
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
        neighbors_dict = {}
        for neighbor_id in all_neighbor_ids:
            neighbor = await self._entity_repo.get(neighbor_id)
            if neighbor:
                neighbors_dict[neighbor_id] = neighbor
        
        entity_levels = {eid: 1 for eid in all_neighbor_ids}
        
        all_nodes = await self._apply_access_control(
            neighbors_dict, entity_levels, user_id, company_id
        )
        
        nodes_by_id = {node.entity_id: node for node in all_nodes}
        
        # Фильтруем по direction
        if direction == "incoming":
            incoming_nodes = [nodes_by_id[eid] for eid in incoming_ids if eid in nodes_by_id]
            outgoing_nodes = []
        elif direction == "outgoing":
            incoming_nodes = []
            outgoing_nodes = [nodes_by_id[eid] for eid in outgoing_ids if eid in nodes_by_id]
        else:  # "both"
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
        """
        Строит карту направленности для быстрого доступа.
        
        Returns:
            {
                "manages": {
                    "is_directed": True,
                    "inverse_type_id": "reports_to",
                    "weight_default": 1.0
                }
            }
        """
        relationship_types = await self._relationship_type_repo.list_all()
        
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
        direction_map: Dict[str, Dict[str, Any]]
    ) -> Tuple[bool, Optional[str]]:
        """
        Проверяет можно ли пройти ребро от from_entity_id.
        
        Returns:
            (can_traverse: bool, target_id: Optional[str])
        """
        rel_info = direction_map.get(relationship.relationship_type)
        if not rel_info:
            logger.warning(f"Unknown relationship_type: {relationship.relationship_type}")
            return False, None
        
        is_directed = rel_info["is_directed"]
        inverse_type_id = rel_info.get("inverse_type_id")
        
        if relationship.source_entity_id == from_entity_id:
            return True, relationship.target_entity_id
        
        if relationship.target_entity_id == from_entity_id:
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
        company_id: Optional[str]
    ) -> List[GraphNode]:
        """
        Применяет access control к entities.
        
        Returns:
            List[GraphNode] с флагом access и placeholder для скрытых
        """
        nodes = []
        for entity_id, entity in entities_dict.items():
            level = entity_levels.get(entity_id, 0)
            
            can_read = await self._access_control.can_read_entity(
                entity, user_id, company_id
            )
            
            if can_read:
                nodes.append(GraphNode(
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    name=entity.name,
                    level=level,
                    access=True,
                    attributes=entity.attributes
                ))
            else:
                nodes.append(GraphNode(
                    entity_id=entity.entity_id,
                    entity_type="hidden",
                    name="Hidden",
                    level=level,
                    access=False,
                    attributes=None
                ))
        
        return nodes
    
    def _build_edges(
        self,
        relationships: List[Relationship],
        direction_map: Dict[str, Dict[str, Any]]
    ) -> List[GraphEdge]:
        """Строит список GraphEdge из relationships"""
        edges = []
        for rel in relationships:
            rel_info = direction_map.get(rel.relationship_type, {})
            is_directed = rel_info.get("is_directed", True)
            
            edges.append(GraphEdge(
                edge_id=rel.relationship_id,
                source_id=rel.source_entity_id,
                target_id=rel.target_entity_id,
                relationship_type=rel.relationship_type,
                weight=rel.weight,
                is_directed=is_directed,
                attributes=rel.attributes
            ))
        
        return edges
    
    async def _dijkstra_shortest_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int,
        direction_map: Dict[str, Dict[str, Any]]
    ) -> Tuple[List[str], float]:
        """
        Weighted Dijkstra для shortest path.
        
        Returns:
            (path: List[str], total_distance: float)
        """
        # Special case: self-loop (from == to)
        if from_id == to_id:
            return [from_id], 0.0
        
        distances = {from_id: 0.0}
        parent = {}
        visited = set()
        
        heap = [(0.0, from_id, 0)]
        
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
            
            relationships = await self._relationship_repo.get_by_entity_for_graph(
                current_id,
                cross_company=True
            )
            
            for rel in relationships:
                can_traverse, neighbor_id = self._can_traverse_edge(
                    rel, current_id, direction_map
                )
                
                if not can_traverse or not neighbor_id or neighbor_id in visited:
                    continue
                
                new_distance = current_dist + rel.weight
                
                if neighbor_id not in distances or new_distance < distances[neighbor_id]:
                    distances[neighbor_id] = new_distance
                    parent[neighbor_id] = current_id
                    heapq.heappush(heap, (new_distance, neighbor_id, current_depth + 1))
        
        return [], 0.0
    
    def _reconstruct_path(
        self,
        parent: Dict[str, str],
        from_id: str,
        to_id: str
    ) -> List[str]:
        """Восстанавливает путь из parent map"""
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
    
    async def _build_path_edges(
        self,
        path: List[str],
        direction_map: Dict[str, Dict[str, Any]]
    ) -> List[GraphEdge]:
        """Строит edges вдоль пути"""
        edges = []
        
        for i in range(len(path) - 1):
            source_id = path[i]
            target_id = path[i + 1]
            
            relationships = await self._relationship_repo.get_by_entity_for_graph(
                source_id,
                cross_company=True
            )
            
            for rel in relationships:
                can_traverse, neighbor_id = self._can_traverse_edge(
                    rel, source_id, direction_map
                )
                
                if can_traverse and neighbor_id == target_id:
                    rel_info = direction_map.get(rel.relationship_type, {})
                    edges.append(GraphEdge(
                        edge_id=rel.relationship_id,
                        source_id=rel.source_entity_id,
                        target_id=rel.target_entity_id,
                        relationship_type=rel.relationship_type,
                        weight=rel.weight,
                        is_directed=rel_info.get("is_directed", True),
                        attributes=rel.attributes
                    ))
                    break
        
        return edges

