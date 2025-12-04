"""
Репозиторий для типов сущностей CRM.
Работает с SQLAlchemy напрямую для эффективных запросов.
"""

import logging
from typing import Optional, List, Type

from sqlalchemy import select, and_, or_

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import EntityType

logger = logging.getLogger(__name__)


class EntityTypeRepository(BaseCRMRepository[EntityType]):
    """
    Репозиторий для типов сущностей.
    
    Системные типы (company_id=None, is_system=True):
    - person, organization, project, task
    
    Кастомные типы создаются для конкретной компании.
    """
    
    def __init__(self, db: CRMDatabase):
        super().__init__(db)
    
    @property
    def model_class(self) -> Type[EntityType]:
        return EntityType
    
    @property
    def id_field(self) -> str:
        return "type_id"
    
    async def get_system_types(self) -> List[EntityType]:
        """Получает все системные типы (is_system=True)"""
        async with self._db.session() as session:
            stmt = select(EntityType).where(EntityType.is_system == True)
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_custom_types(self, company_id: str) -> List[EntityType]:
        """Получает кастомные типы компании"""
        async with self._db.session() as session:
            stmt = select(EntityType).where(
                and_(
                    EntityType.company_id == company_id,
                    EntityType.is_system == False
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_all_for_company(self, company_id: str) -> List[EntityType]:
        """Получает все типы для компании (системные + кастомные)"""
        async with self._db.session() as session:
            stmt = select(EntityType).where(
                or_(
                    EntityType.is_system == True,
                    EntityType.company_id == company_id
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_company(
        self, 
        company_id: str, 
        type_id: str
    ) -> Optional[EntityType]:
        """Получает тип по ID для компании (системный или кастомный)"""
        async with self._db.session() as session:
            stmt = select(EntityType).where(
                and_(
                    EntityType.type_id == type_id,
                    or_(
                        EntityType.is_system == True,
                        EntityType.company_id == company_id
                    )
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def exists(self, type_id: str, company_id: Optional[str] = None) -> bool:
        """Проверяет существование типа"""
        async with self._db.session() as session:
            if company_id:
                stmt = select(EntityType.type_id).where(
                    and_(
                        EntityType.type_id == type_id,
                        or_(
                            EntityType.is_system == True,
                            EntityType.company_id == company_id
                        )
                    )
                )
            else:
                stmt = select(EntityType.type_id).where(
                    EntityType.type_id == type_id
                )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
