"""
Единый сервис задач CRM: создание, получение, обновление статусов.

Типы задач: knowledge_import, note_analyze, note_analysis_draft_repair,
note_markdown_format, daily_summary, period_summary, namespace_integration_job.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal, cast

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.db.models import CRMTask
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.models.api import (
    KnowledgeImportCreatedEntityItem,
    NoteProcessingConfig,
    TaskCreatedEntitiesResponse,
)
from apps.crm.services.crm_task_ws_broadcast import broadcast_crm_task_updated_for_user
from apps.crm.services.entity_service import EntityService
from apps.crm.services.knowledge_import_text_redis import (
    delete_pending_import_text,
    store_pending_import_text,
)
from apps.crm.types import JsonObject
from apps.crm_worker.broker import broker as crm_worker_broker
from apps.crm_worker.task_names import (
    CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN_TASK_NAME,
    CRM_PROCESS_NOTE_TASK_NAME,
    CRM_REBUILD_DAILY_SUMMARY_TASK_NAME,
    CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME,
    CRM_REPAIR_NOTE_ANALYSIS_DRAFT_TASK_NAME,
    CRM_RUN_KNOWLEDGE_IMPORT_TASK_NAME,
    CRM_RUN_NAMESPACE_INTEGRATION_JOB_TASK_NAME,
)
from core.context import clear_context, get_context, resolve_namespace_or_raise, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import User
from core.tasks.kicker import kiq_task_name_with_context
from core.utils.knowledge_text_split import validate_chunk_max_chars

logger = get_logger(__name__)
MAX_SOURCE_TEXT_INLINE_CHARS = 100_000
MAX_SOURCE_FILES_PER_IMPORT = 80
ALL_NAMESPACES_TASK_KEY = "__all_namespaces__"
# Нет ни progress patch, ни смены статуса дольше этого окна → запись считаем потерянной при рестарте воркера.
STALE_CRM_TASK_INACTIVITY = timedelta(minutes=10)

if TYPE_CHECKING:
    from core.db.repositories.company_repository import CompanyRepository
    from core.files.file_repository import FileRepository

KnowledgeImportMode = Literal["notes_only", "graph"]
NamespaceIntegrationJobKind = Literal["entities", "custom_fields"]


def _task_data_str_list(data: JsonObject, key: str) -> list[str]:
    raw = data.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"task data field {key!r} must be list[str]")
    raw_items = cast(list[object], raw)
    out: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            raise ValueError(f"task data field {key!r} must contain only strings")
        out.append(item)
    return out


def _task_data_optional_str(data: JsonObject, key: str) -> str | None:
    raw = data.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"task data field {key!r} must be str")
    return raw


def _task_data_required_str(data: JsonObject, key: str) -> str:
    value = _task_data_optional_str(data, key)
    if value is None or not value.strip():
        raise ValueError(f"Нет {key} в данных задачи для перезапуска")
    return value


def _task_data_int(data: JsonObject, key: str, default: int) -> int:
    raw = data.get(key)
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise ValueError(f"task data field {key!r} must be int")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        return int(raw)
    raise ValueError(f"task data field {key!r} must be int")


def _task_data_bool(data: JsonObject, key: str, default: bool) -> bool:
    raw = data.get(key)
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise ValueError(f"task data field {key!r} must be bool")
    return raw


def _task_data_import_mode(
    data: JsonObject, key: str, default: KnowledgeImportMode
) -> KnowledgeImportMode:
    raw = data.get(key, default)
    if raw == "notes_only":
        return "notes_only"
    if raw == "graph":
        return "graph"
    raise ValueError(f"task data field {key!r} must be notes_only or graph")


class ActiveTaskExistsError(ValueError):
    """Бросается при попытке стартовать задачу, для которой уже есть активная (pending/running)."""

    def __init__(
        self,
        task_type: str,
        existing_task_id: str,
        *,
        dedup: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            f"Задача типа '{task_type}' уже выполняется (task_id={existing_task_id}). Дождитесь завершения или отмените текущую задачу."
        )
        self.task_type: str = task_type
        self.existing_task_id: str = existing_task_id
        self.dedup: dict[str, str] = dict(dedup) if dedup else {}


def _normalize_import_file_ids(
    source_file_id: str | None,
    source_file_ids: list[str] | None,
) -> list[str]:
    legacy = str(source_file_id).strip() if source_file_id else ""
    from_list: list[str] = []
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
    out: list[str] = []
    for s in from_list:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


class TaskService:
    def __init__(
        self,
        task_repo: TaskRepository,
        entity_service: EntityService,
        relationship_repo: RelationshipRepository,
        file_repository: FileRepository,
        company_repository: CompanyRepository,
    ) -> None:
        self._task_repo: TaskRepository = task_repo
        self._entity_service: EntityService = entity_service
        self._relationship_repo: RelationshipRepository = relationship_repo
        self._file_repository: FileRepository = file_repository
        self._company_repository: CompanyRepository = company_repository

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
    def _normalize_task_namespace(namespace: str | None) -> str:
        if namespace is None:
            return ALL_NAMESPACES_TASK_KEY
        normalized = namespace.strip()
        if not normalized:
            return ALL_NAMESPACES_TASK_KEY
        return normalized

    @staticmethod
    def _namespace_for_worker(task_namespace: str) -> str | None:
        if task_namespace == ALL_NAMESPACES_TASK_KEY:
            return None
        return task_namespace

    @staticmethod
    def _auth_token_from_context() -> str | None:
        ctx = get_context()
        return ctx.auth_token if ctx else None

    async def _assert_no_active_task(
        self,
        task_type: str,
        data_key_values: dict[str, str],
        namespace: str,
    ) -> None:
        """Бросает ValueError если уже есть активная (pending/running) задача того же типа с теми же ключами."""
        existing = await self._task_repo.find_active_by_data_keys(
            task_type, data_key_values, namespace, self._get_company_id()
        )
        if existing is not None:
            raise ActiveTaskExistsError(
                task_type,
                existing.task_id,
                dedup=data_key_values,
            )

    # ── Knowledge Import ──────────────────────────────────────────────────────

    async def start_knowledge_import(
        self,
        *,
        namespace: str,
        mode: KnowledgeImportMode,
        source_file_id: str | None,
        source_file_ids: list[str] | None,
        source_text: str | None,
        extract_entity_types: list[str] | None,
        split_by_headings: bool,
        chunk_max_chars: int,
    ) -> CRMTask:
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
        _ = validate_chunk_max_chars(chunk_max_chars)

        ns = namespace.strip()
        await self._entity_service.ensure_namespace_exists(ns)
        await self._assert_no_active_task("knowledge_import", {}, ns)

        task_id = str(uuid.uuid4())
        sha: str | None = None
        if has_text:
            sha = hashlib.sha256(text_raw.encode("utf-8")).hexdigest()
            await store_pending_import_text(task_id, text_raw)

        row = CRMTask(
            task_id=task_id,
            task_type="knowledge_import",
            status="pending",
            stage="pending",
            progress_pct=0,
            company_id=self._get_company_id(),
            namespace=ns,
            user_id=self._get_user_id(),
            data={
                "mode": mode,
                "source_file_id": file_ids[0] if len(file_ids) == 1 else None,
                "source_file_ids": file_ids if len(file_ids) > 1 else [],
                "source_text_sha256": sha,
                "split_by_headings": split_by_headings,
                "chunk_max_chars": chunk_max_chars,
                "extract_entity_types": list(extract_entity_types)
                if extract_entity_types
                else None,
                "notes_created_count": 0,
                "entities_created_count": 0,
                "relationships_created_count": 0,
                "created_entity_ids": [],
                "created_relationship_ids": [],
                "attachment_document_ids": [],
                "review_completed_at": None,
                "chunk_errors": [],
            },
        )
        try:
            _ = await self._task_repo.create(row)
        except Exception:
            if has_text:
                await delete_pending_import_text(task_id)
            raise

        ctx = get_context()
        if ctx is None:
            raise ValueError("Для старта импорта нужен контекст запроса")
        try:
            task = await kiq_task_name_with_context(
                CRM_RUN_KNOWLEDGE_IMPORT_TASK_NAME,
                crm_worker_broker,
                task_id=task_id,
                company_id=row.company_id,
                auth_token=self._auth_token_from_context(),
                interface_language=ctx.language.value,
                background_kind="crm_task",
            )
            taskiq_id = str(task.task_id)
        except Exception as exc:
            await self._task_repo.patch_progress(
                task_id,
                row.company_id,
                status="failed",
                stage="failed",
                progress_pct=0,
                completed_at=datetime.now(UTC),
                error_message=str(exc),
            )
            if has_text:
                await delete_pending_import_text(task_id)
            raise

        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            status="running",
            stage="reading_source",
            progress_pct=10,
            started_at=datetime.now(UTC),
            taskiq_task_id=taskiq_id,
        )
        row.status = "running"
        row.stage = "reading_source"
        row.progress_pct = 10
        row.started_at = datetime.now(UTC)
        row.taskiq_task_id = taskiq_id
        return row

    # ── Интеграции namespace (фоновые джобы по коннектору) ─────────────────────

    async def start_namespace_integration_job(
        self,
        *,
        namespace: str,
        provider_id: str,
        job: NamespaceIntegrationJobKind,
    ) -> CRMTask:
        ns = namespace.strip()
        pid = provider_id.strip()
        if not pid:
            raise ValueError("provider_id обязателен")
        await self._entity_service.ensure_namespace_exists(ns)
        await self._assert_no_active_task(
            "namespace_integration_job",
            {"provider_id": pid, "job": job},
            ns,
        )
        task_id = str(uuid.uuid4())
        row = CRMTask(
            task_id=task_id,
            task_type="namespace_integration_job",
            status="pending",
            stage="pending",
            progress_pct=0,
            company_id=self._get_company_id(),
            namespace=ns,
            user_id=self._get_user_id(),
            data={"provider_id": pid, "job": job, "stats": {}},
        )
        _ = await self._task_repo.create(row)

        ctx = get_context()
        if ctx is None:
            raise ValueError("Для старта фоновой задачи интеграции нужен контекст запроса")
        try:
            task = await kiq_task_name_with_context(
                CRM_RUN_NAMESPACE_INTEGRATION_JOB_TASK_NAME,
                crm_worker_broker,
                task_id=task_id,
                company_id=row.company_id,
                auth_token=self._auth_token_from_context(),
                interface_language=ctx.language.value,
                background_kind="crm_task",
            )
            taskiq_id = str(task.task_id)
        except Exception as exc:
            await self._task_repo.patch_progress(
                task_id,
                row.company_id,
                status="failed",
                stage="failed",
                progress_pct=0,
                completed_at=datetime.now(UTC),
                error_message=str(exc),
            )
            raise

        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            status="running",
            stage="running",
            progress_pct=0,
            started_at=datetime.now(UTC),
            taskiq_task_id=taskiq_id,
        )
        row.status = "running"
        row.stage = "running"
        row.progress_pct = 0
        row.started_at = datetime.now(UTC)
        row.taskiq_task_id = taskiq_id
        return row

    # ── Note Analyze ──────────────────────────────────────────────────────────

    async def start_note_analyze(
        self,
        *,
        note_id: str,
        note_name: str,
        namespace: str,
        mode: str,
        config: NoteProcessingConfig,
    ) -> CRMTask:
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")
        missing_attachment_ids: list[str] = []
        for attachment_id in note.attachment_ids:
            file_record = await self._file_repository.get(attachment_id)
            if file_record is None:
                missing_attachment_ids.append(attachment_id)
        if missing_attachment_ids:
            missing_str = ", ".join(missing_attachment_ids)
            raise ValueError(
                f"Запуск анализа невозможен: у заметки есть вложения без метаданных файла в shared storage ({missing_str})."
            )

        await self._assert_no_active_task("note_analyze", {"note_id": note_id}, namespace)
        task_id = str(uuid.uuid4())
        row = CRMTask(
            task_id=task_id,
            task_type="note_analyze",
            status="pending",
            stage="pending",
            progress_pct=0,
            company_id=self._get_company_id(),
            namespace=namespace,
            user_id=self._get_user_id(),
            data={
                "note_id": note_id,
                "note_name": note_name,
                "mode": mode,
                "config_payload": config.model_dump(mode="json"),
                "result_entities_count": None,
                "result_relationships_count": None,
            },
        )
        _ = await self._task_repo.create(row)

        ctx = get_context()
        if ctx is None:
            raise ValueError("Для старта анализа нужен контекст запроса")
        try:
            task = await kiq_task_name_with_context(
                CRM_PROCESS_NOTE_TASK_NAME,
                crm_worker_broker,
                task_id=task_id,
                note_id=note_id,
                company_id=row.company_id,
                namespace=namespace,
                auth_token=ctx.auth_token,
                user_id=row.user_id,
                interface_language=ctx.language.value,
                config_payload=config.model_dump(mode="json"),
                mode=mode,
                background_kind="crm_task",
            )
            taskiq_id = str(task.task_id)
        except Exception as exc:
            await self._task_repo.patch_progress(
                task_id,
                row.company_id,
                status="failed",
                stage="failed",
                error_message=str(exc),
                completed_at=datetime.now(UTC),
            )
            raise

        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            status="running",
            stage="pending",
            started_at=datetime.now(UTC),
            taskiq_task_id=taskiq_id,
        )
        row.status = "running"
        row.started_at = datetime.now(UTC)
        row.taskiq_task_id = taskiq_id
        return row

    async def start_note_analysis_draft_repair(self, *, note_id: str) -> CRMTask:
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")
        if note.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
            raise ValueError("Ожидалась заметка (entity_type=note)")
        namespace = resolve_namespace_or_raise(note.namespace)
        await self._assert_no_active_task(
            "note_analysis_draft_repair",
            {"note_id": note_id},
            namespace,
        )
        task_id = str(uuid.uuid4())
        row = CRMTask(
            task_id=task_id,
            task_type="note_analysis_draft_repair",
            status="pending",
            stage="pending",
            progress_pct=0,
            company_id=self._get_company_id(),
            namespace=namespace,
            user_id=self._get_user_id(),
            data={
                "note_id": note_id,
                "note_name": note.name or "",
            },
        )
        _ = await self._task_repo.create(row)

        ctx = get_context()
        if ctx is None or ctx.auth_token is None:
            raise ValueError("Для старта починки черновика нужен контекст запроса")
        auth_token = ctx.auth_token
        try:
            task = await kiq_task_name_with_context(
                CRM_REPAIR_NOTE_ANALYSIS_DRAFT_TASK_NAME,
                crm_worker_broker,
                note_id=note_id,
                company_id=row.company_id,
                namespace=namespace,
                auth_token=auth_token,
                user_id=row.user_id,
                interface_language=ctx.language.value,
                task_id=task_id,
                background_kind="crm_task",
            )
            taskiq_id = str(task.task_id)
        except Exception as exc:
            await self._task_repo.patch_progress(
                task_id,
                row.company_id,
                status="failed",
                stage="failed",
                error_message=str(exc),
                completed_at=datetime.now(UTC),
            )
            raise

        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            status="running",
            stage="draft_repair",
            started_at=datetime.now(UTC),
            taskiq_task_id=taskiq_id,
        )
        row.status = "running"
        row.stage = "draft_repair"
        row.started_at = datetime.now(UTC)
        row.taskiq_task_id = taskiq_id
        return row

    async def start_note_markdown_format(
        self,
        *,
        note_id: str,
        expected_updated_at_iso: str,
    ) -> CRMTask:
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError("Заметка не найдена")
        if note.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
            raise ValueError("Ожидалась заметка (entity_type=note)")
        desc = note.description
        if desc is None or not str(desc).strip():
            raise ValueError("Текст заметки пуст")
        ns = resolve_namespace_or_raise(note.namespace)
        await self._assert_no_active_task(
            "note_markdown_format",
            {"note_id": note_id},
            ns,
        )
        task_id = str(uuid.uuid4())
        row = CRMTask(
            task_id=task_id,
            task_type="note_markdown_format",
            status="pending",
            stage="pending",
            progress_pct=0,
            company_id=self._get_company_id(),
            namespace=ns,
            user_id=self._get_user_id(),
            data={
                "note_id": note_id,
                "note_name": note.name or "",
                "expected_updated_at_iso": expected_updated_at_iso,
            },
        )
        _ = await self._task_repo.create(row)

        ctx = get_context()
        if ctx is None or ctx.auth_token is None:
            raise ValueError("Для старта форматирования заметки нужен контекст запроса")
        auth_token = ctx.auth_token
        try:
            task = await kiq_task_name_with_context(
                CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN_TASK_NAME,
                crm_worker_broker,
                note_id=note_id,
                company_id=row.company_id,
                namespace=ns,
                auth_token=auth_token,
                user_id=row.user_id,
                interface_language=ctx.language.value,
                expected_updated_at_iso=expected_updated_at_iso,
                task_id=task_id,
                background_kind="crm_task",
            )
            taskiq_id = str(task.task_id)
        except Exception as exc:
            await self._task_repo.patch_progress(
                task_id,
                row.company_id,
                status="failed",
                stage="failed",
                error_message=str(exc),
                completed_at=datetime.now(UTC),
            )
            raise

        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            status="running",
            stage="format_markdown",
            started_at=datetime.now(UTC),
            taskiq_task_id=taskiq_id,
        )
        row.status = "running"
        row.stage = "format_markdown"
        row.started_at = datetime.now(UTC)
        row.taskiq_task_id = taskiq_id
        return row

    # ── Common ────────────────────────────────────────────────────────────────

    async def get_task(self, task_id: str) -> CRMTask | None:
        return await self._task_repo.get(task_id)

    async def list_tasks(
        self,
        namespace: str | None,
        *,
        task_type: str | None = None,
        note_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CRMTask]:
        ns = namespace.strip() if isinstance(namespace, str) and namespace.strip() else None
        return await self._task_repo.list_for_namespace(
            ns, task_type=task_type, note_id=note_id, limit=limit, offset=offset
        )

    async def count_tasks(
        self,
        namespace: str | None,
        *,
        task_type: str | None = None,
        note_id: str | None = None,
    ) -> int:
        ns = namespace.strip() if isinstance(namespace, str) and namespace.strip() else None
        return await self._task_repo.count_for_namespace(ns, task_type=task_type, note_id=note_id)

    async def request_cancel(self, task_id: str) -> CRMTask:
        row = await self._task_repo.get(task_id)
        if row is None:
            raise ValueError(f"Задача не найдена: {task_id}")
        if row.user_id != self._get_user_id():
            raise ValueError("Отменить может только инициатор задачи")
        if row.status in ("completed", "failed", "rolled_back", "cancelled"):
            raise ValueError(f"Задача в статусе {row.status}, отмена недоступна")

        if row.cancel_requested and row.status in ("pending", "running"):
            now = datetime.now(UTC)
            pct = int(row.progress_pct)
            await self._task_repo.patch_progress(
                task_id,
                row.company_id,
                status="cancelled",
                stage="cancelled",
                progress_pct=pct,
                completed_at=now,
                cancel_requested=False,
            )
            updated = await self._task_repo.get(task_id)
            if updated is None:
                raise ValueError(f"Задача не найдена: {task_id}")
            await broadcast_crm_task_updated_for_user(user_id=updated.user_id, row=updated)
            return updated

        await self._task_repo.patch_progress(task_id, row.company_id, cancel_requested=True)
        row.cancel_requested = True
        return row

    async def reconcile_stale_worker_tasks(self) -> int:
        """Закрывает зависшие active-задачи и отмены, которые воркер не обработал.

        Порядок: сначала все ``pending``/``running`` с ``cancel_requested`` → ``cancelled`` (без
        ожидания ``STALE_CRM_TASK_INACTIVITY``), затем строки без активности дольше порога →
        ``failed`` или ``cancelled``.

        Вызывается при старте процесса ``crm_worker`` (до reclaim Redis) и HTTP-сервиса ``crm``.
        """
        cutoff = datetime.now(UTC) - STALE_CRM_TASK_INACTIVITY
        cancel_rows = await self._task_repo.reconcile_cancel_requested_active_tasks()
        stale_rows = await self._task_repo.reconcile_stale_active_tasks_older_than(cutoff=cutoff)
        rows = cancel_rows + stale_rows
        if not rows:
            return 0
        for row in rows:
            if (
                row.task_type in ("note_analyze", "note_analysis_draft_repair")
                and row.status == "failed"
            ):
                raw_note = row.data.get("note_id")
                note_id = raw_note if isinstance(raw_note, str) and raw_note else None
                if note_id:
                    company_row = await self._company_repository.get(row.company_id)
                    if company_row is None:
                        logger.warning(
                            "crm.reconcile_stale_task.company_missing task_id=%s company_id=%s",
                            row.task_id,
                            row.company_id,
                        )
                    else:
                        set_context(
                            Context(
                                user=User(user_id=row.user_id, name="CRM worker"),
                                active_company=company_row,
                                session_id=f"crm-reconcile:{row.company_id}",
                                channel="taskiq",
                                active_namespace=row.namespace,
                                language=Language.RU,
                            )
                        )
                        try:
                            await self._entity_service.record_note_analysis_failure(
                                note_id,
                                row.error_message or "",
                            )
                        finally:
                            clear_context()
            await broadcast_crm_task_updated_for_user(user_id=row.user_id, row=row)
        logger.info("crm.tasks.reconcile_stale_finished reconciled=%s", len(rows))
        return len(rows)

    async def rollback_task(self, task_id: str) -> CRMTask:
        row = await self._task_repo.get(task_id)
        if row is None:
            raise ValueError(f"Задача не найдена: {task_id}")
        if row.task_type != "knowledge_import":
            raise ValueError("Откат доступен только для задач типа knowledge_import")
        if row.user_id != self._get_user_id():
            raise ValueError("Откатить может только инициатор задачи")
        if row.status == "rolled_back":
            raise ValueError("Задача уже откачена")
        if row.status == "running":
            raise ValueError("Дождитесь завершения или отмените задачу перед откатом")
        created_entity_ids = _task_data_str_list(row.data, "created_entity_ids")
        created_relationship_ids = _task_data_str_list(row.data, "created_relationship_ids")
        if not created_entity_ids and not created_relationship_ids:
            raise ValueError("Нет созданных сущностей или связей для отката")

        for rid in reversed(created_relationship_ids):
            _ = await self._relationship_repo.delete_by_relationship_id(rid)

        for eid in reversed(created_entity_ids):
            _ = await self._entity_service.delete_entity(eid)

        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            status="rolled_back",
            completed_at=datetime.now(UTC),
        )
        row.status = "rolled_back"
        row.completed_at = datetime.now(UTC)
        logger.info("task rolled_back task_id=%s", task_id)
        return row

    async def get_task_created_entities(self, task_id: str) -> TaskCreatedEntitiesResponse:
        row = await self._task_repo.get(task_id)
        if row is None:
            raise LookupError(task_id)
        if row.user_id != self._get_user_id():
            raise ValueError("Просматривать список может только инициатор задачи")
        if row.task_type != "knowledge_import":
            raise ValueError("Список сущностей доступен только для задач knowledge_import")
        if row.status not in ("completed", "failed", "cancelled"):
            raise ValueError(
                f"Список созданных сущностей доступен для статусов completed, failed, cancelled; сейчас {row.status}"
            )
        raw_ids = _task_data_str_list(row.data, "created_entity_ids")
        rel_n = len(_task_data_str_list(row.data, "created_relationship_ids"))
        if len(raw_ids) == 0 and rel_n == 0:
            raise ValueError("У задачи нет созданных сущностей или связей")

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
        return TaskCreatedEntitiesResponse(
            task_id=row.task_id,
            namespace=row.namespace,
            status=row.status,
            review_completed_at=_task_data_optional_str(row.data, "review_completed_at"),
            relationships_created_count=_task_data_int(row.data, "relationships_created_count", 0),
            entities=items,
            missing_entity_ids=missing,
        )

    async def complete_task_review(self, task_id: str) -> CRMTask:
        row = await self._task_repo.get(task_id)
        if row is None:
            raise LookupError(task_id)
        if row.user_id != self._get_user_id():
            raise ValueError("Подтвердить просмотр может только инициатор задачи")
        if row.task_type != "knowledge_import":
            raise ValueError("Ревью доступно только для задач knowledge_import")
        if row.data.get("review_completed_at") is not None:
            return row
        if row.status not in ("completed", "failed", "cancelled"):
            raise ValueError(
                f"Подтверждение доступно для статусов completed, failed, cancelled; сейчас {row.status}"
            )
        ent_n = len(_task_data_str_list(row.data, "created_entity_ids"))
        rel_n = len(_task_data_str_list(row.data, "created_relationship_ids"))
        if ent_n == 0 and rel_n == 0:
            raise ValueError("Нет созданных сущностей или связей для подтверждения просмотра")
        now = datetime.now(UTC)
        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            data_patch={"review_completed_at": now.isoformat()},
        )
        row.data["review_completed_at"] = now.isoformat()
        return row

    # ── Дневная / периодическая сводка ─────────────────────────────────────────────────

    async def start_daily_summary(
        self,
        *,
        namespace: str | None,
        date_str: str,
        reason: str = "manual",
    ) -> CRMTask:
        ns = self._normalize_task_namespace(namespace)
        worker_namespace = self._namespace_for_worker(ns)
        await self._assert_no_active_task("daily_summary", {"date_str": date_str}, ns)
        task_id = str(uuid.uuid4())
        row = CRMTask(
            task_id=task_id,
            task_type="daily_summary",
            status="pending",
            stage="pending",
            progress_pct=0,
            company_id=self._get_company_id(),
            namespace=ns,
            user_id=self._get_user_id(),
            data={"date_str": date_str, "reason": reason},
        )
        _ = await self._task_repo.create(row)

        ctx = get_context()
        if ctx is None:
            raise ValueError("Для старта сводки нужен контекст запроса")
        try:
            task = await kiq_task_name_with_context(
                CRM_REBUILD_DAILY_SUMMARY_TASK_NAME,
                crm_worker_broker,
                company_id=row.company_id,
                date_str=date_str,
                namespace=worker_namespace,
                reason=reason,
                auth_token=ctx.auth_token,
                user_id=row.user_id,
                task_id=task_id,
                background_kind="crm_task",
            )
            taskiq_id = str(task.task_id)
        except Exception as exc:
            await self._task_repo.patch_progress(
                task_id,
                row.company_id,
                status="failed",
                stage="failed",
                error_message=str(exc),
                completed_at=datetime.now(UTC),
            )
            raise

        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            status="running",
            stage="summarizing_day",
            progress_pct=10,
            started_at=datetime.now(UTC),
            taskiq_task_id=taskiq_id,
        )
        row.status = "running"
        row.started_at = datetime.now(UTC)
        row.taskiq_task_id = taskiq_id
        return row

    async def start_period_summary(
        self,
        *,
        namespace: str | None,
        date_from: str,
        date_to: str,
        reason: str = "manual",
    ) -> CRMTask:
        ns = self._normalize_task_namespace(namespace)
        worker_namespace = self._namespace_for_worker(ns)
        await self._assert_no_active_task(
            "period_summary", {"date_from": date_from, "date_to": date_to}, ns
        )
        task_id = str(uuid.uuid4())
        row = CRMTask(
            task_id=task_id,
            task_type="period_summary",
            status="pending",
            stage="pending",
            progress_pct=0,
            company_id=self._get_company_id(),
            namespace=ns,
            user_id=self._get_user_id(),
            data={"date_from": date_from, "date_to": date_to, "reason": reason},
        )
        _ = await self._task_repo.create(row)

        ctx = get_context()
        if ctx is None:
            raise ValueError("Для старта сводки нужен контекст запроса")
        try:
            task = await kiq_task_name_with_context(
                CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME,
                crm_worker_broker,
                company_id=row.company_id,
                date_from=date_from,
                date_to=date_to,
                namespace=worker_namespace,
                reason=reason,
                auth_token=ctx.auth_token,
                user_id=row.user_id,
                task_id=task_id,
                background_kind="crm_task",
            )
            taskiq_id = str(task.task_id)
        except Exception as exc:
            await self._task_repo.patch_progress(
                task_id,
                row.company_id,
                status="failed",
                stage="failed",
                error_message=str(exc),
                completed_at=datetime.now(UTC),
            )
            raise

        await self._task_repo.patch_progress(
            task_id,
            row.company_id,
            status="running",
            stage="summarizing_day",
            progress_pct=10,
            started_at=datetime.now(UTC),
            taskiq_task_id=taskiq_id,
        )
        row.status = "running"
        row.started_at = datetime.now(UTC)
        row.taskiq_task_id = taskiq_id
        return row

    # ── Retry ─────────────────────────────────────────────────────────────────

    async def retry_task(self, task_id: str) -> CRMTask:
        """Перезапустить failed/cancelled задачу с теми же параметрами."""
        old = await self._task_repo.get(task_id)
        if old is None:
            raise LookupError(task_id)
        if old.status not in ("failed", "cancelled"):
            raise ValueError(
                f"Перезапуск доступен только для failed/cancelled, сейчас: {old.status}"
            )
        match old.task_type:
            case "knowledge_import":
                return await self._retry_knowledge_import(old)
            case "note_analyze":
                return await self._retry_note_analyze(old)
            case "note_analysis_draft_repair":
                return await self._retry_note_analysis_draft_repair(old)
            case "note_markdown_format":
                return await self._retry_note_markdown_format(old)
            case "daily_summary":
                return await self._retry_daily_summary(old)
            case "period_summary":
                return await self._retry_period_summary(old)
            case "namespace_integration_job":
                return await self._retry_namespace_integration_job(old)
            case _:
                raise ValueError(f"Перезапуск для типа '{old.task_type}' не поддерживается")

    async def _retry_knowledge_import(self, old: CRMTask) -> CRMTask:
        data = old.data
        return await self.start_knowledge_import(
            namespace=old.namespace,
            mode=_task_data_import_mode(data, "mode", "notes_only"),
            source_file_id=_task_data_optional_str(data, "source_file_id"),
            source_file_ids=_task_data_str_list(data, "source_file_ids") or None,
            source_text=None,
            extract_entity_types=_task_data_str_list(data, "extract_entity_types") or None,
            split_by_headings=_task_data_bool(data, "split_by_headings", False),
            chunk_max_chars=_task_data_int(data, "chunk_max_chars", 50_000),
        )

    async def _retry_note_analyze(self, old: CRMTask) -> CRMTask:
        data = old.data
        note_id = _task_data_required_str(data, "note_id")
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")
        config_payload = data.get("config_payload")
        if config_payload is None:
            config_payload = {}
        elif not isinstance(config_payload, dict):
            raise ValueError("task data field 'config_payload' must be object")
        config = NoteProcessingConfig.model_validate(config_payload)
        return await self.start_note_analyze(
            note_id=note_id,
            note_name=note.name or "",
            namespace=old.namespace,
            mode=_task_data_required_str(data, "mode"),
            config=config,
        )

    async def _retry_note_analysis_draft_repair(self, old: CRMTask) -> CRMTask:
        data = old.data
        note_id = _task_data_required_str(data, "note_id")
        return await self.start_note_analysis_draft_repair(note_id=note_id)

    async def _retry_note_markdown_format(self, old: CRMTask) -> CRMTask:
        data = old.data
        note_id = _task_data_required_str(data, "note_id")
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")
        return await self.start_note_markdown_format(
            note_id=note_id,
            expected_updated_at_iso=note.updated_at.isoformat(),
        )

    async def _retry_daily_summary(self, old: CRMTask) -> CRMTask:
        data = old.data
        date_str = _task_data_required_str(data, "date_str")
        return await self.start_daily_summary(
            namespace=old.namespace,
            date_str=date_str,
            reason="retry",
        )

    async def _retry_period_summary(self, old: CRMTask) -> CRMTask:
        data = old.data
        date_from = _task_data_required_str(data, "date_from")
        date_to = _task_data_required_str(data, "date_to")
        return await self.start_period_summary(
            namespace=old.namespace,
            date_from=date_from,
            date_to=date_to,
            reason="retry",
        )

    async def _retry_namespace_integration_job(self, old: CRMTask) -> CRMTask:
        data = old.data
        provider_raw = data.get("provider_id")
        job_raw = data.get("job")
        if not isinstance(provider_raw, str) or not provider_raw.strip():
            raise ValueError("Нет provider_id в данных задачи интеграции")
        if job_raw not in ("entities", "custom_fields"):
            raise ValueError("Нет корректного job в данных задачи интеграции")
        job: NamespaceIntegrationJobKind = job_raw
        return await self.start_namespace_integration_job(
            namespace=old.namespace,
            provider_id=provider_raw.strip(),
            job=job,
        )
