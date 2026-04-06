"""
Импорт базы знаний: старт job, статус, отмена, откат.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from apps.crm.db.models import CRMKnowledgeImport
from apps.crm.db.repositories.knowledge_import_repository import KnowledgeImportRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.models.api import (
    KnowledgeImportCreatedEntitiesResponse,
    KnowledgeImportCreatedEntityItem,
)
from apps.crm.services.entity_service import EntityService
from apps.crm.services.knowledge_import_text_redis import (
    delete_pending_import_text,
    store_pending_import_text,
)
from core.context import get_context
from core.utils.knowledge_text_split import validate_chunk_max_chars

logger = logging.getLogger(__name__)

MAX_SOURCE_TEXT_INLINE_CHARS = 100_000
MAX_SOURCE_FILES_PER_IMPORT = 80

KnowledgeImportMode = Literal["notes_only", "graph"]


def _normalize_import_file_ids(
    source_file_id: Optional[str],
    source_file_ids: Optional[List[str]],
) -> List[str]:
    legacy = str(source_file_id).strip() if source_file_id else ""
    from_list: List[str] = []
    if source_file_ids:
        for x in source_file_ids:
            s = str(x).strip()
            if s:
                from_list.append(s)
    if legacy:
        if from_list:
            raise ValueError("Нельзя одновременно передавать source_file_id и source_file_ids")
        return [legacy]
    seen: set[str] = set()
    out: List[str] = []
    for s in from_list:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


class KnowledgeImportService:
    def __init__(
        self,
        import_repo: KnowledgeImportRepository,
        entity_service: EntityService,
        relationship_repo: RelationshipRepository,
    ) -> None:
        self._import_repo = import_repo
        self._entity_service = entity_service
        self._relationship_repo = relationship_repo

    def _get_company_id(self) -> str:
        ctx = get_context()
        if not ctx or not ctx.active_company:
            raise ValueError("Нет активной компании в контексте")
        return ctx.active_company.company_id

    def _get_user_id(self) -> str:
        ctx = get_context()
        if not ctx or not ctx.user:
            raise ValueError("Нет пользователя в контексте")
        return ctx.user.user_id

    @staticmethod
    def _auth_token_from_context() -> Optional[str]:
        ctx = get_context()
        if not ctx:
            return None
        return ctx.auth_token

    async def start_import(
        self,
        *,
        namespace: str,
        mode: KnowledgeImportMode,
        source_file_id: Optional[str],
        source_file_ids: Optional[List[str]],
        source_text: Optional[str],
        extract_entity_types: Optional[List[str]],
        split_by_headings: bool,
        chunk_max_chars: int,
    ) -> CRMKnowledgeImport:
        if mode not in ("notes_only", "graph"):
            raise ValueError(f"Неизвестный mode: {mode}")
        file_ids = _normalize_import_file_ids(source_file_id, source_file_ids)
        text_raw = source_text if source_text is not None else ""
        if len(text_raw) > MAX_SOURCE_TEXT_INLINE_CHARS:
            raise ValueError(
                f"Текст длиннее {MAX_SOURCE_TEXT_INLINE_CHARS} символов: загрузите часть как файлы"
            )
        text_stripped = text_raw.strip()
        has_text = len(text_stripped) > 0
        has_files = len(file_ids) > 0
        if not has_text and not has_files:
            raise ValueError("Укажите непустой текст или хотя бы один файл")
        if len(file_ids) > MAX_SOURCE_FILES_PER_IMPORT:
            raise ValueError(f"Не больше {MAX_SOURCE_FILES_PER_IMPORT} файлов за один импорт")
        validate_chunk_max_chars(chunk_max_chars)

        ns = namespace.strip()
        await self._entity_service._ensure_namespace_exists(ns)

        import_id = str(uuid.uuid4())
        sha: Optional[str] = None
        if has_text:
            sha = hashlib.sha256(text_raw.encode("utf-8")).hexdigest()
            await store_pending_import_text(import_id, text_raw)

        row = CRMKnowledgeImport(
            import_id=import_id,
            company_id=self._get_company_id(),
            namespace=ns,
            user_id=self._get_user_id(),
            mode=mode,
            status="pending",
            extract_entity_types=list(extract_entity_types) if extract_entity_types else None,
            source_file_id=file_ids[0] if len(file_ids) == 1 else None,
            source_file_ids=file_ids if len(file_ids) > 1 else None,
            source_text_sha256=sha,
            split_by_headings=split_by_headings,
            chunk_max_chars=chunk_max_chars,
        )
        try:
            await self._import_repo.create(row)
        except Exception:
            if has_text:
                await delete_pending_import_text(import_id)
            raise

        from apps.crm_worker.tasks.knowledge_import_tasks import run_knowledge_import_task

        try:
            task = await run_knowledge_import_task.kiq(
                import_id=import_id,
                company_id=row.company_id,
                auth_token=self._auth_token_from_context(),
            )
            task_id_str = str(task.task_id)
        except Exception as exc:
            await self._import_repo.patch_progress(
                import_id,
                row.company_id,
                status="failed",
                completed_at=datetime.now(timezone.utc),
                error_message=str(exc),
            )
            if has_text:
                await delete_pending_import_text(import_id)
            raise

        await self._import_repo.patch_progress(
            import_id,
            row.company_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            taskiq_task_id=task_id_str,
        )
        row.status = "running"
        row.started_at = datetime.now(timezone.utc)
        row.taskiq_task_id = task_id_str
        return row

    async def get_import(self, import_id: str) -> Optional[CRMKnowledgeImport]:
        return await self._import_repo.get(import_id)

    async def list_imports(self, namespace: str, *, limit: int = 50) -> List[CRMKnowledgeImport]:
        return await self._import_repo.list_for_namespace(namespace.strip(), limit=limit)

    async def request_cancel(self, import_id: str) -> CRMKnowledgeImport:
        row = await self._import_repo.get(import_id)
        if row is None:
            raise ValueError(f"Импорт не найден: {import_id}")
        if row.user_id != self._get_user_id():
            raise ValueError("Отменить может только инициатор импорта")
        if row.status in ("completed", "failed", "rolled_back", "cancelled"):
            raise ValueError(f"Импорт в статусе {row.status}, отмена недоступна")
        await self._import_repo.patch_progress(import_id, row.company_id, cancel_requested=True)
        row.cancel_requested = True
        return row

    async def rollback_import(self, import_id: str) -> CRMKnowledgeImport:
        row = await self._import_repo.get(import_id)
        if row is None:
            raise ValueError(f"Импорт не найден: {import_id}")
        if row.user_id != self._get_user_id():
            raise ValueError("Откатить может только инициатор импорта")
        if row.status == "rolled_back":
            raise ValueError("Импорт уже откачен")
        if row.status == "running":
            raise ValueError("Дождитесь завершения или отмените импорт перед откатом")
        if not row.created_entity_ids and not row.created_relationship_ids:
            raise ValueError("Нет созданных сущностей или связей для отката")

        rel_ids = list(row.created_relationship_ids or [])
        for rid in reversed(rel_ids):
            await self._relationship_repo.delete_by_relationship_id(rid)

        ent_ids = list(row.created_entity_ids or [])
        for eid in reversed(ent_ids):
            await self._entity_service.delete_entity(eid)

        await self._import_repo.patch_progress(
            import_id,
            row.company_id,
            status="rolled_back",
            completed_at=datetime.now(timezone.utc),
        )
        row.status = "rolled_back"
        row.completed_at = datetime.now(timezone.utc)
        logger.info("knowledge_import rolled_back import_id=%s", import_id)
        return row

    async def get_import_created_entities(self, import_id: str) -> KnowledgeImportCreatedEntitiesResponse:
        row = await self._import_repo.get(import_id)
        if row is None:
            raise LookupError(import_id)
        if row.user_id != self._get_user_id():
            raise ValueError("Просматривать список может только инициатор импорта")
        if row.status not in ("completed", "failed", "cancelled"):
            raise ValueError(
                f"Список созданных сущностей доступен для статусов completed, failed, cancelled; сейчас {row.status}"
            )
        raw_ids = list(row.created_entity_ids or [])
        rel_n = len(row.created_relationship_ids or [])
        if len(raw_ids) == 0 and rel_n == 0:
            raise ValueError("У импорта нет созданных сущностей или связей")

        entities = await self._entity_service.list_entities_by_ids_ordered(raw_ids)
        found_ids = {e.entity_id for e in entities}
        missing = [eid for eid in raw_ids if eid not in found_ids]
        items = [
            KnowledgeImportCreatedEntityItem(
                entity_id=e.entity_id,
                name=e.name,
                entity_type=e.entity_type,
                entity_subtype=e.entity_subtype,
                status=e.status,
            )
            for e in entities
        ]
        return KnowledgeImportCreatedEntitiesResponse(
            import_id=row.import_id,
            namespace=row.namespace,
            status=row.status,
            review_completed_at=row.review_completed_at,
            relationships_created_count=int(row.relationships_created_count or 0),
            entities=items,
            missing_entity_ids=missing,
        )

    async def complete_import_review(self, import_id: str) -> CRMKnowledgeImport:
        row = await self._import_repo.get(import_id)
        if row is None:
            raise LookupError(import_id)
        if row.user_id != self._get_user_id():
            raise ValueError("Подтвердить просмотр может только инициатор импорта")
        if row.review_completed_at is not None:
            return row
        if row.status not in ("completed", "failed", "cancelled"):
            raise ValueError(
                f"Подтверждение доступно для статусов completed, failed, cancelled; сейчас {row.status}"
            )
        ent_n = len(row.created_entity_ids or [])
        rel_n = len(row.created_relationship_ids or [])
        if ent_n == 0 and rel_n == 0:
            raise ValueError("Нет созданных сущностей или связей для подтверждения просмотра")
        now = datetime.now(timezone.utc)
        await self._import_repo.patch_progress(
            import_id,
            row.company_id,
            review_completed_at=now,
        )
        row.review_completed_at = now
        return row
