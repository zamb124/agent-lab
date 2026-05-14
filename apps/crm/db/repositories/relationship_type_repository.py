"""
Репозиторий для RelationshipType.

ВСЕ типы с company_id (ОБЯЗАТЕЛЬНО)!
"""

from typing import List

from sqlalchemy import and_, func, select

from apps.crm.db.base import BaseCRMRepository
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
        include_system: bool = True,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RelationshipType]:
        """Типы связей, доступные для компании (только строки с company_id из контекста)."""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            cond = [RelationshipType.company_id == company_id]
            if not include_system:
                cond.append(not RelationshipType.is_system)
            stmt = select(RelationshipType).where(and_(*cond)).limit(limit).offset(offset)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_all_for_company(
        self,
        include_system: bool = True,
    ) -> int:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            cond = [RelationshipType.company_id == company_id]
            if not include_system:
                cond.append(not RelationshipType.is_system)
            stmt = select(func.count()).select_from(RelationshipType).where(and_(*cond))
            result = await session.execute(stmt)
            return result.scalar() or 0

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

