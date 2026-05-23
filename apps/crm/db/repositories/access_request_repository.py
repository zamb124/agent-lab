"""
Репозиторий для запросов на доступ.
"""

from typing import override

from sqlalchemy import delete, func, select, update

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import AccessRequest
from core.db.utils import get_rowcount


class AccessRequestRepository(BaseCRMRepository[AccessRequest]):
    """
    Репозиторий для работы с запросами на доступ.
    """

    def __init__(self, db: CRMDatabase):
        super().__init__(db)

    @property
    @override
    def model_class(self) -> type[AccessRequest]:
        return AccessRequest

    @property
    @override
    def id_field(self) -> str:
        return "access_request_id"

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
            return get_rowcount(result)

    async def deduplicate_pending_entity_requests(
        self,
        entity_id: str,
    ) -> None:
        """Оставляет один pending-запрос на (requester, entity), остальные удаляет."""
        pending = await self._fetch_pending_entity_requests(entity_id)
        seen: set[tuple[str, str]] = set()
        to_delete: list[str] = []
        for r in pending:
            key = (r.requester_id, r.resource_id)
            if key not in seen:
                seen.add(key)
                continue
            to_delete.append(r.access_request_id)
        if not to_delete:
            return
        async with self._db.session() as session:
            for access_request_id in to_delete:
                result = await session.execute(
                    delete(AccessRequest).where(
                        AccessRequest.access_request_id == access_request_id
                    )
                )
                if get_rowcount(result) != 1:
                    raise ValueError(f"Access request {access_request_id} was not deleted")
            await session.commit()

    async def _fetch_pending_entity_requests(self, entity_id: str) -> list[AccessRequest]:
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

    @override
    async def create(self, entity: AccessRequest) -> AccessRequest:
        """Создает запрос на доступ"""
        async with self._db.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity

    async def list_by_company(
        self,
        company_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AccessRequest]:
        async with self._db.session() as session:
            stmt = (
                select(AccessRequest)
                .where(AccessRequest.company_id == company_id)
                .order_by(AccessRequest.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_by_company_and_status(
        self,
        company_id: str,
        status: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AccessRequest]:
        async with self._db.session() as session:
            stmt = (
                select(AccessRequest)
                .where(AccessRequest.company_id == company_id, AccessRequest.status == status)
                .order_by(AccessRequest.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_by_company(
        self,
        company_id: str,
        status: str | None = None,
    ) -> int:
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(AccessRequest)
                .where(AccessRequest.company_id == company_id)
            )
            if status is not None:
                stmt = stmt.where(AccessRequest.status == status)
            result = await session.execute(stmt)
            return result.scalar() or 0
