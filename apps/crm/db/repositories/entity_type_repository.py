"""
Репозиторий для EntityType с поддержкой иерархии.

Системные типы (note, task) + пользовательские типы.
ВСЕ типы с company_id (ОБЯЗАТЕЛЬНО)!
"""

from typing import List, Optional
from sqlalchemy import func, select, update as sa_update, or_

from apps.crm.db.base import CRMDatabase, BaseCRMRepository
from apps.crm.db.models import EntityType
from core.logging import get_logger

logger = get_logger(__name__)


class EntityTypeRepository(BaseCRMRepository[EntityType]):
    """Репозиторий для типов сущностей"""
    
    @property
    def model_class(self) -> type[EntityType]:
        return EntityType
    
    @property
    def id_field(self) -> str:
        return "type_id"
    
    async def get_all_for_company(
        self,
        include_system: bool = True,
        namespace: Optional[str] = None,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[EntityType]:
        """Типы, доступные для компании из контекста."""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(EntityType).where(EntityType.company_id == company_id)
            if namespace:
                stmt = stmt.where(
                    or_(
                        EntityType.namespace_ids.contains([namespace]),
                        EntityType.namespace_ids.contains(["*"]),
                    )
                )
            stmt = (
                stmt.order_by(EntityType.is_system.desc(), EntityType.type_id.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_all_for_company(
        self,
        namespace: Optional[str] = None,
    ) -> int:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(EntityType).where(EntityType.company_id == company_id)
            if namespace:
                stmt = stmt.where(
                    or_(
                        EntityType.namespace_ids.contains([namespace]),
                        EntityType.namespace_ids.contains(["*"]),
                    )
                )
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def get_by_type_id(
        self,
        type_id: str,
        company_id: Optional[str] = None
    ) -> Optional[EntityType]:
        """Получает тип по type_id в рамках компании."""
        effective_company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(EntityType).where(
                EntityType.type_id == type_id,
                EntityType.company_id == effective_company_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_allowed_for_namespace(
        self,
        namespace: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[EntityType]:
        """Возвращает типы, разрешенные в конкретном namespace."""
        return await self.get_all_for_company(namespace=namespace, limit=limit, offset=offset)
    
    async def update_metadata(
        self,
        type_id: str,
        company_id: str | None = None,
        **fields: object,
    ) -> None:
        """Обновляет указанные поля entity type через SQL UPDATE (без session.merge)."""
        company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                sa_update(EntityType)
                .where(
                    EntityType.type_id == type_id,
                    EntityType.company_id == company_id,
                )
                .values(**fields)
            )
            await session.execute(stmt)
            await session.commit()

    async def update_color(self, type_id: str, color: str) -> None:
        """Точечное обновление цвета без session.merge (не затрагивает namespace_ids)."""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                sa_update(EntityType)
                .where(
                    EntityType.type_id == type_id,
                    EntityType.company_id == company_id,
                )
                .values(color=color)
            )
            await session.execute(stmt)
            await session.commit()

    async def set_namespace_ids(
        self,
        type_id: str,
        namespace_ids: list[str],
    ) -> EntityType:
        """Атомарная полная замена namespace_ids (SELECT FOR UPDATE)."""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(EntityType)
                .where(
                    EntityType.type_id == type_id,
                    EntityType.company_id == company_id,
                )
                .with_for_update()
            )
            result = await session.execute(stmt)
            entity_type = result.scalar_one_or_none()
            if not entity_type:
                raise ValueError(f"EntityType '{type_id}' not found for company '{company_id}'")

            entity_type.namespace_ids = sorted(namespace_ids)

            await session.commit()
            await session.refresh(entity_type)
            return entity_type

    async def add_namespace_ids(
        self,
        type_id: str,
        namespace_ids: list[str],
        company_id: str | None = None,
    ) -> EntityType:
        """Атомарно добавляет namespace_ids к entity type (SELECT FOR UPDATE)."""
        company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(EntityType)
                .where(
                    EntityType.type_id == type_id,
                    EntityType.company_id == company_id,
                )
                .with_for_update()
            )
            result = await session.execute(stmt)
            entity_type = result.scalar_one_or_none()
            if not entity_type:
                raise ValueError(f"EntityType '{type_id}' not found for company '{company_id}'")

            current = set(entity_type.namespace_ids or [])
            current.update(namespace_ids)
            entity_type.namespace_ids = sorted(current)

            await session.commit()
            await session.refresh(entity_type)
            return entity_type

    async def remove_namespace_ids(
        self,
        type_id: str,
        namespace_ids: list[str],
    ) -> EntityType:
        """Атомарно удаляет namespace_ids из entity type (SELECT FOR UPDATE)."""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(EntityType)
                .where(
                    EntityType.type_id == type_id,
                    EntityType.company_id == company_id,
                )
                .with_for_update()
            )
            result = await session.execute(stmt)
            entity_type = result.scalar_one_or_none()
            if not entity_type:
                raise ValueError(f"EntityType '{type_id}' not found for company '{company_id}'")

            current = set(entity_type.namespace_ids or [])
            current -= set(namespace_ids)
            entity_type.namespace_ids = sorted(current)

            await session.commit()
            await session.refresh(entity_type)
            return entity_type

    async def create_custom_type(
        self,
        type_data: EntityType,
        company_id: str
    ) -> EntityType:
        """
        Создает кастомный тип для компании.
        
        Системные типы создавать нельзя!
        """
        if type_data.is_system:
            raise ValueError("Cannot create system type through this method")
        
        type_data.company_id = company_id
        return await self.create(type_data)

