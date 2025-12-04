"""
Репозиторий для связей между сущностями CRM.
Работает с SQLAlchemy напрямую для эффективных запросов.
"""

import logging
from typing import List, Type

from sqlalchemy import select, and_, or_

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import Relationship

logger = logging.getLogger(__name__)


class RelationshipRepository(BaseCRMRepository[Relationship]):
    """
    Репозиторий для связей между сущностями.
    Использует индексы для быстрого поиска по source/target.
    """
    
    def __init__(self, db: CRMDatabase):
        super().__init__(db)
    
    @property
    def model_class(self) -> Type[Relationship]:
        return Relationship
    
    @property
    def id_field(self) -> str:
        return "relationship_id"
    
    async def get_by_company(
        self, 
        company_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Relationship]:
        """Получает связи компании с пагинацией"""
        async with self._db.session() as session:
            stmt = (
                select(Relationship)
                .where(Relationship.company_id == company_id)
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_entity(
        self, 
        company_id: str, 
        entity_id: str
    ) -> List[Relationship]:
        """Получает все связи сущности (как source или target)"""
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                and_(
                    Relationship.company_id == company_id,
                    or_(
                        Relationship.source_entity_id == entity_id,
                        Relationship.target_entity_id == entity_id
                    )
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_source(
        self, 
        company_id: str, 
        source_entity_id: str
    ) -> List[Relationship]:
        """Получает связи, где сущность - источник"""
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                and_(
                    Relationship.company_id == company_id,
                    Relationship.source_entity_id == source_entity_id
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_target(
        self, 
        company_id: str, 
        target_entity_id: str
    ) -> List[Relationship]:
        """Получает связи, где сущность - цель"""
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                and_(
                    Relationship.company_id == company_id,
                    Relationship.target_entity_id == target_entity_id
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_type(
        self, 
        company_id: str, 
        relationship_type: str
    ) -> List[Relationship]:
        """Получает связи определенного типа"""
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                and_(
                    Relationship.company_id == company_id,
                    Relationship.relationship_type == relationship_type
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_between(
        self, 
        company_id: str,
        entity_id_1: str, 
        entity_id_2: str
    ) -> List[Relationship]:
        """Получает связи между двумя сущностями (в любом направлении)"""
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                and_(
                    Relationship.company_id == company_id,
                    or_(
                        and_(
                            Relationship.source_entity_id == entity_id_1,
                            Relationship.target_entity_id == entity_id_2
                        ),
                        and_(
                            Relationship.source_entity_id == entity_id_2,
                            Relationship.target_entity_id == entity_id_1
                        )
                    )
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def delete_by_entity(self, company_id: str, entity_id: str) -> int:
        """Удаляет все связи сущности"""
        from sqlalchemy import delete as sql_delete
        
        async with self._db.session() as session:
            stmt = sql_delete(Relationship).where(
                and_(
                    Relationship.company_id == company_id,
                    or_(
                        Relationship.source_entity_id == entity_id,
                        Relationship.target_entity_id == entity_id
                    )
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
