"""Репозиторий для работы с пространствами (SQLAlchemy)."""

import logging
from typing import List, Optional, Type

from sqlalchemy import select

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncSpace

logger = logging.getLogger(__name__)


class SpaceRepository(BaseSyncRepository[SyncSpace]):
    """Репозиторий для пространств с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase):
        super().__init__(db=db)

    @property
    def model_class(self) -> Type[SyncSpace]:
        return SyncSpace

    @property
    def id_field(self) -> str:
        return "space_id"

    async def get_by_name(self, name: str, company_id: Optional[str] = None) -> Optional[SyncSpace]:
        """Находит пространство по имени внутри компании."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(SyncSpace).where(
                SyncSpace.company_id == cid,
                SyncSpace.name == name,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_namespace(
        self,
        namespace: str,
        company_id: Optional[str] = None,
    ) -> Optional[SyncSpace]:
        """Находит пространство по платформенному namespace внутри компании."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(SyncSpace).where(
                SyncSpace.company_id == cid,
                SyncSpace.namespace == namespace,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def exists_for_namespace(
        self,
        namespace: str,
        company_id: Optional[str] = None,
    ) -> bool:
        """Проверяет, занят ли уже namespace другим пространством в компании."""
        return await self.get_by_namespace(namespace, company_id=company_id) is not None

    async def list_by_user(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None,
    ) -> List[SyncSpace]:
        """Пространства, созданные конкретным пользователем."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(SyncSpace)
                .where(SyncSpace.company_id == cid, SyncSpace.created_by_user_id == user_id)
                .order_by(SyncSpace.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
