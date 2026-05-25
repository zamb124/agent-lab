from dataclasses import dataclass
from typing import override

from sqlalchemy import func, select, update

from apps.crm.db.base import BaseCRMRepository
from apps.crm.db.models import CRMSuggest
from core.context import get_context


@dataclass(frozen=True)
class CRMSuggestPage:
    items: list[CRMSuggest]
    total: int
    limit: int
    offset: int


class SuggestRepository(BaseCRMRepository[CRMSuggest]):
    @property
    @override
    def model_class(self) -> type[CRMSuggest]:
        return CRMSuggest

    @property
    @override
    def id_field(self) -> str:
        return "suggest_id"

    @override
    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    @override
    async def get(
        self,
        suggest_id: str,
        /,
        *,
        namespace: str | None = None,
    ) -> CRMSuggest | None:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMSuggest).where(
                CRMSuggest.suggest_id == suggest_id,
                CRMSuggest.company_id == company_id,
            )
            if namespace is not None:
                stmt = stmt.where(CRMSuggest.namespace == namespace)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_suggests(
        self,
        namespace: str,
        status: str | None = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> CRMSuggestPage:
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

            return CRMSuggestPage(items=items, total=total, limit=limit, offset=offset)

    @override
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
        namespace: str | None = None,
    ) -> CRMSuggest | None:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                update(CRMSuggest)
                .where(CRMSuggest.suggest_id == suggest_id, CRMSuggest.company_id == company_id)
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
    ) -> CRMSuggest | None:
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

    async def find_by_targets_batch(
        self,
        *,
        namespace: str,
        suggest_type: str,
        target_entity_ids_batches: list[list[str]],
        statuses: set[str],
    ) -> dict[tuple[str, ...], CRMSuggest]:
        """
        Batched версия `find_by_targets` для перебора пар в `suggest_service`.

        Раньше `suggest_service._generate_duplicate_suggests` дёргал `find_by_targets`
        в цикле по каждой найденной паре entity-кандидат (до 250+ запросов на
        company-scan). Этот метод одним запросом достаёт все совпадения и
        возвращает map `tuple(sorted_target_ids) -> latest CRMSuggest`.

        Ключ map нормализован тем же sort + strip, что используется в insert
        (`_create_suggest`), поэтому caller обращается через `tuple(sorted(...))`.
        """
        if not target_entity_ids_batches:
            return {}
        if not statuses:
            raise ValueError("statuses are required")

        company_id = self._get_company_id()
        normalized_batches: list[list[str]] = []
        for batch in target_entity_ids_batches:
            normalized_batch = sorted({item.strip() for item in batch if item.strip()})
            if normalized_batch:
                normalized_batches.append(normalized_batch)
        if not normalized_batches:
            return {}

        async with self._db.session() as session:
            stmt = (
                select(CRMSuggest)
                .where(
                    CRMSuggest.company_id == company_id,
                    CRMSuggest.namespace == namespace,
                    CRMSuggest.suggest_type == suggest_type,
                    CRMSuggest.target_entity_ids.in_(normalized_batches),
                    CRMSuggest.status.in_(sorted(statuses)),
                )
                .order_by(CRMSuggest.created_at.desc())
            )
            result = await session.execute(stmt)
            rows: list[CRMSuggest] = list(result.scalars().all())

        latest_by_targets: dict[tuple[str, ...], CRMSuggest] = {}
        for row in rows:
            key = tuple(row.target_entity_ids)
            if key not in latest_by_targets:
                latest_by_targets[key] = row
        return latest_by_targets
