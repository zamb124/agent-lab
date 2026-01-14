"""
Репозиторий для relationships (граф связей).

Для сложных связей с метаданными.
Все связи ТОЛЬКО здесь (нет linked_entity_ids в ChromaDB)!
"""

from typing import List, Optional, Dict
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crm.db.base import CRMDatabase, BaseCRMRepository
from apps.crm.db.models import Relationship
from core.logging import get_logger

logger = get_logger(__name__)


class RelationshipRepository(BaseCRMRepository[Relationship]):
    """Репозиторий для relationships в PostgreSQL"""
    
    @property
    def model_class(self) -> type[Relationship]:
        return Relationship
    
    @property
    def id_field(self) -> str:
        return "relationship_id"
    
    async def get_by_entity(
        self,
        entity_id: str
    ) -> List[Relationship]:
        """Получает все связи сущности (source и target)"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                or_(
                    Relationship.source_entity_id == entity_id,
                    Relationship.target_entity_id == entity_id
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_entity_for_graph(
        self,
        entity_id: str,
        cross_company: bool = False
    ) -> List[Relationship]:
        """
        Получает relationships для graph traversal.
        
        Args:
            entity_id: ID entity
            cross_company: Если True - игнорирует company_id фильтр
                          (для cross-company графов через grants)
        
        Returns:
            List relationships где entity_id участвует (source или target)
        """
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                or_(
                    Relationship.source_entity_id == entity_id,
                    Relationship.target_entity_id == entity_id
                )
            )
            
            if not cross_company:
                company_id = self._get_company_id()
                stmt = stmt.where(Relationship.company_id == company_id)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def find_exact(
        self,
        source_id: str,
        target_id: str,
        rel_type: str
    ) -> Optional[Relationship]:
        """Находит точную связь"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.source_entity_id == source_id,
                Relationship.target_entity_id == target_id,
                Relationship.relationship_type == rel_type
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def delete_by_entity(
        self,
        entity_id: str
    ) -> int:
        """Удаляет все связи сущности"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = delete(Relationship).where(
                Relationship.company_id == company_id,
                or_(
                    Relationship.source_entity_id == entity_id,
                    Relationship.target_entity_id == entity_id
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            
            logger.info(f"Deleted {result.rowcount} relationships for entity:{entity_id}")
            return result.rowcount
    
    async def get_by_type(
        self,
        relationship_type: str,
        limit: int = 100
    ) -> List[Relationship]:
        """Получает связи по типу"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.relationship_type == relationship_type
            ).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_outgoing(
        self,
        source_entity_id: str,
        relationship_type: Optional[str] = None
    ) -> List[Relationship]:
        """Получает исходящие связи от сущности"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.source_entity_id == source_entity_id
            )
            
            if relationship_type:
                stmt = stmt.where(Relationship.relationship_type == relationship_type)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_incoming(
        self,
        target_entity_id: str,
        relationship_type: Optional[str] = None
    ) -> List[Relationship]:
        """Получает входящие связи к сущности"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.target_entity_id == target_entity_id
            )
            
            if relationship_type:
                stmt = stmt.where(Relationship.relationship_type == relationship_type)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_neighbors(
        self,
        entity_ids: List[str],
        relationship_types: Optional[List[str]] = None
    ) -> Dict[str, List[Relationship]]:
        """
        Batch получение соседей для списка entities.
        
        Args:
            entity_ids: Список ID entities
            relationship_types: Фильтр по типам связей (опционально)
        
        Returns:
            Dict где ключ - entity_id, значение - список relationships
        """
        if not entity_ids:
            return {}
        
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                or_(
                    Relationship.source_entity_id.in_(entity_ids),
                    Relationship.target_entity_id.in_(entity_ids)
                )
            )
            
            if relationship_types:
                stmt = stmt.where(Relationship.relationship_type.in_(relationship_types))
            
            result = await session.execute(stmt)
            relationships = list(result.scalars().all())
            
            neighbors_map: Dict[str, List[Relationship]] = {eid: [] for eid in entity_ids}
            for rel in relationships:
                if rel.source_entity_id in entity_ids:
                    neighbors_map[rel.source_entity_id].append(rel)
                if rel.target_entity_id in entity_ids:
                    neighbors_map[rel.target_entity_id].append(rel)
            
            logger.debug(f"Loaded neighbors for {len(entity_ids)} entities: {len(relationships)} relationships")
            return neighbors_map
    
    async def get_all_for_graph(
        self,
        limit: int = 10000
    ) -> List[Relationship]:
        """
        Получить ВСЕ relationships компании для построения полного графа.
        
        ВНИМАНИЕ: Использовать ТОЛЬКО если нужен весь граф в памяти.
        Может вернуть тысячи relationships.
        
        Args:
            limit: Максимальное количество relationships
        
        Returns:
            Список всех relationships компании
        """
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id
            ).limit(limit)
            
            result = await session.execute(stmt)
            relationships = list(result.scalars().all())
            
            logger.info(f"Loaded {len(relationships)} relationships for graph (limit={limit})")
            return relationships

