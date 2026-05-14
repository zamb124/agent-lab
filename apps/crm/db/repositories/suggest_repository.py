from typing import Optional

from sqlalchemy import func, select, update

from apps.crm.db.base import BaseCRMRepository
from apps.crm.db.models import CRMSuggest
from core.context import get_context
from core.pagination import OffsetPage


class SuggestRepository(BaseCRMRepository[CRMSuggest]):
    @property
    def model_class(self) -> type[CRMSuggest]:
        return CRMSuggest

    @property
    def id_field(self) -> str:
        return "id"

    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    async def get(
        self,
        suggest_id: str,
        *,
        namespace: Optional[str] = None,
    ) -> Optional[CRMSuggest]:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMSuggest).where(
                CRMSuggest.id == suggest_id,
                CRMSuggest.company_id == company_id,
            )
            if namespace is not None:
                stmt = stmt.where(CRMSuggest.namespace == namespace)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_suggests(
        self,
        namespace: str,
        status: Optional[str] = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> OffsetPage:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMSuggest).where(
                CRMSuggest.company_id == company_id,
                CRMSuggest.namespace == namespace,
            )
            if status:
                stmt = stmt.where(CRMSuggest.status == status)

            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = await session.scalar(count_stmt) or 0

            stmt = stmt.order_by(CRMSuggest.created_at.desc()).limit(limit).offset(offset)
            result = await session.execute(stmt)
            items = list(result.scalars().all())

            return OffsetPage(items=items, total=total, limit=limit, offset=offset)

    async def create(self, entity: CRMSuggest) -> CRMSuggest:
        async with self._db.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
        return entity

    async def update_status(
        self,
        suggest_id: str,
        new_status: str,
        *,
        namespace: Optional[str] = None,
    ) -> Optional[CRMSuggest]:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                update(CRMSuggest)
                .where(CRMSuggest.id == suggest_id, CRMSuggest.company_id == company_id)
                .values(status=new_status)
                .returning(CRMSuggest)
            )
            if namespace is not None:
                stmt = stmt.where(CRMSuggest.namespace == namespace)
            result = await session.execute(stmt)
            await session.commit()
            return result.scalar_one_or_none()

    async def find_by_targets(
        self,
        *,
        namespace: str,
        suggest_type: str,
        target_entity_ids: list[str],
        statuses: set[str],
    ) -> Optional[CRMSuggest]:
        company_id = self._get_company_id()
        normalized_target_ids = sorted({item.strip() for item in target_entity_ids if item.strip()})
        if not normalized_target_ids:
            raise ValueError("target_entity_ids are required")
        if not statuses:
            raise ValueError("statuses are required")

        async with self._db.session() as session:
            stmt = (
                select(CRMSuggest)
                .where(
                    CRMSuggest.company_id == company_id,
                    CRMSuggest.namespace == namespace,
                    CRMSuggest.suggest_type == suggest_type,
                    CRMSuggest.target_entity_ids == normalized_target_ids,
                    CRMSuggest.status.in_(sorted(statuses)),
                )
                .order_by(CRMSuggest.created_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
