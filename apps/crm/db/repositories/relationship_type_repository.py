"""
Репозиторий для RelationshipType.

ВСЕ типы с company_id (ОБЯЗАТЕЛЬНО)!
"""

from typing import List, Optional
from sqlalchemy import select, or_

from apps.crm.db.base import CRMDatabase, BaseCRMRepository
from apps.crm.db.models import RelationshipType
from core.logging import get_logger

logger = get_logger(__name__)


class RelationshipTypeRepository(BaseCRMRepository[RelationshipType]):
    """Репозиторий для типов связей"""
    
    @property
    def model_class(self) -> type[RelationshipType]:
        return RelationshipType
    
    @property
    def id_field(self) -> str:
        return "type_id"
    
    async def get_all_for_company(
        self,
        include_system: bool = True
    ) -> List[RelationshipType]:
        """
        Получает все типы связей доступные для компании.
        
        Args:
            include_system: Включать системные типы (mentions, linked)
        
        Returns:
            Список типов (системные + кастомные компании)
        """
        company_id = self._get_company_id()
        async with self._db.session() as session:
            conditions = [RelationshipType.company_id == company_id]
            
            if include_system:
                conditions.append(
                    or_(
                        RelationshipType.company_id.is_(None),
                        RelationshipType.is_system == True
                    )
                )
            
            stmt = select(RelationshipType).where(or_(*conditions))
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_system_types(self) -> List[RelationshipType]:
        """Получает системные типы (mentions, linked)"""
        async with self._db.session() as session:
            stmt = select(RelationshipType).where(RelationshipType.is_system == True)
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_with_prompts(
        self
    ) -> List[RelationshipType]:
        """
        Типы связей с заполненным prompt для AI-анализа.
        
        Фильтр: company_id из контекста + prompt IS NOT NULL.
        Типы без промпта (linked, child_of, blocked_by, duplicates) не попадают в AI.
        """
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(RelationshipType).where(
                RelationshipType.company_id == company_id,
                RelationshipType.prompt.is_not(None)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def create_custom_type(
        self,
        type_data: RelationshipType
    ) -> RelationshipType:
        """
        Создает кастомный тип связи для компании.
        
        Системные типы создавать нельзя!
        """
        if type_data.is_system:
            raise ValueError("Cannot create system type through this method")
        
        company_id = self._get_company_id()
        type_data.company_id = company_id
        return await self.create(type_data)

