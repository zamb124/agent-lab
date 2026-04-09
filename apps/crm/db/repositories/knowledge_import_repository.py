"""
Репозиторий журнала импорта базы знаний (crm_knowledge_imports).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import func, select, update

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import CRMKnowledgeImport
from core.context import get_context


class KnowledgeImportRepository(BaseCRMRepository[CRMKnowledgeImport]):
    @property
    def model_class(self) -> type[CRMKnowledgeImport]:
        return CRMKnowledgeImport

    @property
    def id_field(self) -> str:
        return "import_id"

    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    async def create(self, row: CRMKnowledgeImport) -> CRMKnowledgeImport:
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def get(self, import_id: str, *, company_id: Optional[str] = None) -> Optional[CRMKnowledgeImport]:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMKnowledgeImport).where(
                CRMKnowledgeImport.import_id == import_id,
                CRMKnowledgeImport.company_id == cid,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_for_worker(self, import_id: str, company_id: str) -> Optional[CRMKnowledgeImport]:
        async with self._db.session() as session:
            stmt = select(CRMKnowledgeImport).where(
                CRMKnowledgeImport.import_id == import_id,
                CRMKnowledgeImport.company_id == company_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def patch_progress(
        self,
        import_id: str,
        company_id: str,
        *,
        status: Optional[str] = None,
        notes_created_count: Optional[int] = None,
        entities_created_count: Optional[int] = None,
        relationships_created_count: Optional[int] = None,
        created_entity_ids: Optional[List[str]] = None,
        created_relationship_ids: Optional[List[str]] = None,
        cancel_requested: Optional[bool] = None,
        error_message: Optional[str] = None,
        chunk_errors: Optional[List[dict[str, Any]]] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        taskiq_task_id: Optional[str] = None,
        review_completed_at: Optional[datetime] = None,
    ) -> None:
        values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if status is not None:
            values["status"] = status
        if notes_created_count is not None:
            values["notes_created_count"] = notes_created_count
        if entities_created_count is not None:
            values["entities_created_count"] = entities_created_count
        if relationships_created_count is not None:
            values["relationships_created_count"] = relationships_created_count
        if created_entity_ids is not None:
            values["created_entity_ids"] = created_entity_ids
        if created_relationship_ids is not None:
            values["created_relationship_ids"] = created_relationship_ids
        if cancel_requested is not None:
            values["cancel_requested"] = cancel_requested
        if error_message is not None:
            values["error_message"] = error_message
        if chunk_errors is not None:
            values["chunk_errors"] = chunk_errors
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        if taskiq_task_id is not None:
            values["taskiq_task_id"] = taskiq_task_id
        if review_completed_at is not None:
            values["review_completed_at"] = review_completed_at

        async with self._db.session() as session:
            await session.execute(
                update(CRMKnowledgeImport)
                .where(
                    CRMKnowledgeImport.import_id == import_id,
                    CRMKnowledgeImport.company_id == company_id,
                )
                .values(**values)
            )
            await session.commit()

    async def list_for_namespace(
        self,
        namespace: str,
        *,
        limit: int = 50,
        company_id: Optional[str] = None,
    ) -> List[CRMKnowledgeImport]:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(CRMKnowledgeImport)
                .where(
                    CRMKnowledgeImport.company_id == cid,
                    CRMKnowledgeImport.namespace == namespace,
                )
                .order_by(CRMKnowledgeImport.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_imports_in_progress_for_namespace(
        self,
        namespace: str,
        *,
        company_id: Optional[str] = None,
    ) -> int:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(CRMKnowledgeImport).where(
                CRMKnowledgeImport.company_id == cid,
                CRMKnowledgeImport.namespace == namespace,
                CRMKnowledgeImport.status.in_(("pending", "running")),
            )
            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Knowledge import in_progress count returned empty")
            return int(value)

    async def count_imports_awaiting_review_for_namespace(
        self,
        namespace: str,
        *,
        company_id: Optional[str] = None,
    ) -> int:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(CRMKnowledgeImport).where(
                CRMKnowledgeImport.company_id == cid,
                CRMKnowledgeImport.namespace == namespace,
                CRMKnowledgeImport.status.in_(("completed", "failed", "cancelled")),
                CRMKnowledgeImport.review_completed_at.is_(None),
            )
            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Knowledge import awaiting_review count returned empty")
            return int(value)
