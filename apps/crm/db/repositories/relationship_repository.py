"""
Репозиторий для relationships (граф связей).

Для сложных связей с метаданными.
Все связи ТОЛЬКО здесь (нет linked_entity_ids в CRMEntity)!
"""

from typing import List, Optional, Dict
from sqlalchemy import select, delete, or_, update

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
    
    async def delete_outgoing_by_source_and_types(
        self,
        source_entity_id: str,
        relationship_types: List[str],
    ) -> int:
        """Удаляет исходящие связи от source с указанными типами."""
        if not relationship_types:
            return 0
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = delete(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.source_entity_id == source_entity_id,
                Relationship.relationship_type.in_(relationship_types),
            )
            result = await session.execute(stmt)
            await session.commit()
            return int(result.rowcount or 0)

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

    async def rewrite_entity_id(
        self,
        company_id: str,
        old_entity_id: str,
        new_entity_id: str,
    ) -> int:
        """
        Заменяет old_entity_id на new_entity_id в source и target.
        Возвращает суммарное число затронутых строк (две операции UPDATE).
        """
        if old_entity_id == new_entity_id:
            raise ValueError("old_entity_id и new_entity_id должны различаться")
        async with self._db.session() as session:
            res_src = await session.execute(
                update(Relationship)
                .where(
                    Relationship.company_id == company_id,
                    Relationship.source_entity_id == old_entity_id,
                )
                .values(source_entity_id=new_entity_id)
            )
            res_tgt = await session.execute(
                update(Relationship)
                .where(
                    Relationship.company_id == company_id,
                    Relationship.target_entity_id == old_entity_id,
                )
                .values(target_entity_id=new_entity_id)
            )
            await session.commit()
            n_src = int(res_src.rowcount or 0)
            n_tgt = int(res_tgt.rowcount or 0)
            logger.info(
                f"Rewrote entity_id {old_entity_id} -> {new_entity_id}: "
                f"source_rows={n_src} target_rows={n_tgt}"
            )
            return n_src + n_tgt

    async def delete_by_relationship_id(self, relationship_id: str) -> bool:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = delete(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.relationship_id == relationship_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return int(result.rowcount or 0) > 0

    async def deduplicate_relationships_for_entity(self, entity_id: str) -> None:
        """
        Удаляет петли source==target и дубликаты по ключу
        (namespace, source, target, relationship_type), оставляя запись с минимальным relationship_id.
        """
        company_id = self._get_company_id()
        rels = await self.get_by_entity(entity_id)
        loops = [r for r in rels if r.source_entity_id == r.target_entity_id]
        for r in loops:
            await self.delete_by_relationship_id(r.relationship_id)

        rels = await self.get_by_entity(entity_id)
        groups: Dict[tuple[str, str, str, str], List[Relationship]] = {}
        for r in rels:
            key = (
                r.namespace,
                r.source_entity_id,
                r.target_entity_id,
                r.relationship_type,
            )
            groups.setdefault(key, []).append(r)
        for group in groups.values():
            if len(group) <= 1:
                continue
            keeper = min(group, key=lambda x: x.relationship_id)
            for r in group:
                if r.relationship_id != keeper.relationship_id:
                    await self.delete_by_relationship_id(r.relationship_id)

