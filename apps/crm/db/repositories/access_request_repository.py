"""
Репозиторий для запросов на доступ.
"""

from typing import List, Optional, Type

from sqlalchemy import func, select, update, delete

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import AccessRequest


class AccessRequestRepository(BaseCRMRepository[AccessRequest]):
    """
    Репозиторий для работы с запросами на доступ.
    """
    
    def __init__(self, db: CRMDatabase):
        super().__init__(db)
    
    @property
    def model_class(self) -> Type[AccessRequest]:
        return AccessRequest
    
    @property
    def id_field(self) -> str:
        return "request_id"
    
    async def remap_entity_resource_id(
        self,
        company_id: str,
        old_entity_id: str,
        new_entity_id: str,
    ) -> int:
        if old_entity_id == new_entity_id:
            raise ValueError("old_entity_id и new_entity_id должны различаться")
        async with self._db.session() as session:
            result = await session.execute(
                update(AccessRequest)
                .where(
                    AccessRequest.company_id == company_id,
                    AccessRequest.resource_type == "entity",
                    AccessRequest.resource_id == old_entity_id,
                )
                .values(resource_id=new_entity_id)
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def deduplicate_pending_entity_requests(
        self,
        entity_id: str,
    ) -> None:
        """Оставляет один pending-запрос на (requester, entity), остальные удаляет."""
        pending = await self._fetch_pending_entity_requests(entity_id)
        seen: set[tuple[str, str]] = set()
        to_delete: List[str] = []
        for r in pending:
            key = (r.requester_id, r.resource_id)
            if key not in seen:
                seen.add(key)
                continue
            to_delete.append(r.request_id)
        if not to_delete:
            return
        async with self._db.session() as session:
            for rid in to_delete:
                await session.execute(
                    delete(AccessRequest).where(AccessRequest.request_id == rid)
                )
            await session.commit()

    async def _fetch_pending_entity_requests(self, entity_id: str) -> List[AccessRequest]:
        async with self._db.session() as session:
            stmt = (
                select(AccessRequest)
                .where(
                    AccessRequest.resource_type == "entity",
                    AccessRequest.resource_id == entity_id,
                    AccessRequest.status == "pending",
                )
                .order_by(AccessRequest.created_at.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def create(self, request: AccessRequest) -> AccessRequest:
        """Создает запрос на доступ"""
        async with self._db.session() as session:
            session.add(request)
            await session.commit()
            await session.refresh(request)
            return request
    
    async def list_by_company(
        self,
        company_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AccessRequest]:
        async with self._db.session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.company_id == company_id
            ).order_by(AccessRequest.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_by_company_and_status(
        self,
        company_id: str,
        status: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AccessRequest]:
        async with self._db.session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.company_id == company_id,
                AccessRequest.status == status
            ).order_by(AccessRequest.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_by_company(
        self,
        company_id: str,
        status: Optional[str] = None,
    ) -> int:
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(AccessRequest).where(
                AccessRequest.company_id == company_id
            )
            if status is not None:
                stmt = stmt.where(AccessRequest.status == status)
            result = await session.execute(stmt)
            return result.scalar() or 0

