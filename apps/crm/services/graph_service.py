"""
GraphService - построение Knowledge Graph для визуализации связей.
"""

import logging
from typing import List, Dict, Any, Optional, Set

from core.context import get_context
from apps.crm.services.entity_service import EntityService
from apps.crm.services.relationship_service import RelationshipService

logger = logging.getLogger(__name__)


class GraphService:
    """
    Сервис для построения Knowledge Graph.
    
    Формирует данные для визуализации графа связей между сущностями.
    """
    
    def __init__(
        self,
        entity_service: EntityService,
        relationship_service: RelationshipService,
    ):
        self._entity_service = entity_service
        self._relationship_service = relationship_service
    
    def _get_company_id(self) -> str:
        """Получает company_id из контекста"""
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    async def get_full_graph(
        self,
        entity_types: Optional[List[str]] = None,
        limit: int = 500,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получает полный граф связей.
        
        Returns:
            {
                "nodes": [
                    {"id": "...", "type": "person", "name": "...", "color": "..."},
                    ...
                ],
                "edges": [
                    {"source": "...", "target": "...", "type": "...", "weight": 1.0},
                    ...
                ]
            }
        """
        company_id = company_id or self._get_company_id()
        
        entities = await self._entity_service.list_entities(
            entity_type=None,
            limit=limit,
            company_id=company_id
        )
        
        if entity_types:
            entities = [e for e in entities if e.type in entity_types]
        
        relationships = await self._relationship_service.list_relationships(
            limit=limit * 2,
            company_id=company_id
        )
        
        entity_ids = {e.entity_id for e in entities}
        relationships = [
            r for r in relationships 
            if r.source_entity_id in entity_ids and r.target_entity_id in entity_ids
        ]
        
        type_info = await self._get_type_info(company_id)
        degree_count = self._count_degrees(relationships)
        
        nodes = [self._build_node(e, type_info, degree_count) for e in entities]
        
        edges = [
            {
                "relationship_id": r.relationship_id,
                "source": r.source_entity_id,
                "target": r.target_entity_id,
                "type": r.relationship_type,
                "weight": r.weight,
            }
            for r in relationships
        ]
        
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            }
        }
    
    async def get_entity_graph(
        self,
        entity_id: str,
        depth: int = 2,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получает граф связей для конкретной сущности.
        
        Args:
            entity_id: ID центральной сущности
            depth: Глубина обхода (1 = только прямые связи)
            
        Returns:
            Граф с центральной сущностью и связанными
        """
        company_id = company_id or self._get_company_id()
        
        visited_ids: Set[str] = set()
        entities_to_fetch: Set[str] = {entity_id}
        all_relationships = []
        
        for _ in range(depth):
            new_ids: Set[str] = set()
            
            for eid in entities_to_fetch:
                if eid in visited_ids:
                    continue
                
                visited_ids.add(eid)
                
                rels = await self._relationship_service.get_entity_relationships(
                    eid, company_id
                )
                all_relationships.extend(rels)
                
                for r in rels:
                    if r.source_entity_id not in visited_ids:
                        new_ids.add(r.source_entity_id)
                    if r.target_entity_id not in visited_ids:
                        new_ids.add(r.target_entity_id)
            
            entities_to_fetch = new_ids
        
        entities = []
        for eid in visited_ids:
            entity = await self._entity_service.get_entity(eid, company_id)
            if entity:
                entities.append(entity)
        
        seen_rels: Set[str] = set()
        unique_relationships = []
        for r in all_relationships:
            if r.relationship_id not in seen_rels:
                seen_rels.add(r.relationship_id)
                unique_relationships.append(r)
        
        type_info = await self._get_type_info(company_id)
        degree_count = self._count_degrees(unique_relationships)
        
        nodes = [
            self._build_node(e, type_info, degree_count, is_center=(e.entity_id == entity_id))
            for e in entities
        ]
        
        edges = [
            {
                "relationship_id": r.relationship_id,
                "source": r.source_entity_id,
                "target": r.target_entity_id,
                "type": r.relationship_type,
                "weight": r.weight,
            }
            for r in unique_relationships
        ]
        
        return {
            "nodes": nodes,
            "edges": edges,
            "center_entity_id": entity_id,
            "depth": depth,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            }
        }
    
    async def get_relationship_types(
        self,
        company_id: Optional[str] = None
    ) -> List[str]:
        """Получает все уникальные типы связей"""
        company_id = company_id or self._get_company_id()
        
        relationships = await self._relationship_service.list_relationships(
            limit=1000,
            company_id=company_id
        )
        
        types = set(r.relationship_type for r in relationships)
        return sorted(types)
    
    async def _get_type_info(self, company_id: str) -> Dict[str, Dict[str, Any]]:
        """Получает информацию о типах сущностей (цвет, коэффициент)"""
        from apps.crm.container import get_crm_container
        
        container = get_crm_container()
        types = await container.entity_type_service.get_all_types(company_id)
        
        return {
            t.type_id: {
                "color": t.color or "#999999",
                "weight_coefficient": t.weight_coefficient if hasattr(t, 'weight_coefficient') else 1.0,
            }
            for t in types
        }
    
    def _count_degrees(self, relationships: List) -> Dict[str, int]:
        """Подсчитывает количество связей для каждой сущности"""
        degree_count = {}
        for r in relationships:
            degree_count[r.source_entity_id] = degree_count.get(r.source_entity_id, 0) + 1
            degree_count[r.target_entity_id] = degree_count.get(r.target_entity_id, 0) + 1
        return degree_count
    
    def _calculate_entity_score(
        self,
        relevance: float,
        degree: int,
        type_coefficient: float
    ) -> tuple[float, float]:
        """
        Рассчитывает score и size для сущности.
        
        Формула: score = relevance * (1 + degree) * type_coefficient
        
        Args:
            relevance: AI-оценка важности (0.0-1.0)
            degree: Количество связей
            type_coefficient: Коэффициент типа сущности
            
        Returns:
            (score, size) - округленные значения
        """
        score = relevance * (1 + degree) * type_coefficient
        size = min(50, max(15, 15 + score * 10))
        return round(score, 2), round(size, 1)
    
    def _build_node(
        self,
        entity,
        type_info: Dict[str, Dict[str, Any]],
        degree_count: Dict[str, int],
        is_center: bool = False
    ) -> Dict[str, Any]:
        """Строит данные ноды для графа"""
        entity_type = entity.type
        type_data = type_info.get(entity_type, {})
        
        relevance = getattr(entity, "relevance", 0.5) or 0.5
        degree = degree_count.get(entity.entity_id, 0)
        type_coefficient = type_data.get("weight_coefficient", 1.0)
        color = type_data.get("color", "#999999")
        
        score, size = self._calculate_entity_score(relevance, degree, type_coefficient)
        
        node = {
            "id": entity.entity_id,
            "type": entity_type,
            "name": entity.name,
            "color": color,
            "attributes": entity.attributes,
            "relevance": relevance,
            "degree": degree,
            "score": score,
            "size": size,
        }
        
        if is_center:
            node["is_center"] = True
        
        return node

