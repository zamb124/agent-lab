"""Постановка фоновой задачи форматирования Markdown для заметки (TaskIQ)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from apps.crm.config import get_crm_settings
from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.task import CRMTask
from apps.crm.services.crm_note_broadcast import broadcast_crm_note_event
from apps.crm_worker.tasks.task_names import CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN
from core.authz.service import AuthzService
from core.context import get_context, resolve_namespace_or_raise
from core.logging import get_logger
from core.tasks import enqueue
from core.test_scope import (
    MOCK_LLM_SIDE_EFFECT_NOTE_MARKDOWN,
    mock_llm_side_effect_enqueue_labels,
)

logger = get_logger(__name__)


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


def _company_id() -> str:
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("No active company in context")
    return ctx.active_company.company_id


def _user_id() -> str:
    ctx = get_context()
    if ctx is None:
        raise ValueError("No user in context")
    return ctx.user.user_id


async def begin_note_markdown_format(*, note_id: str) -> CRMTask:
    note = await CRMEntity.get(note_id)
    if note is None:
        raise ValueError("Note not found")
    if note.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
        raise ValueError("Expected a note (entity_type=note)")
    desc = note.description
    if desc is None or not str(desc).strip():
        raise ValueError("Note text is empty")
    ns = resolve_namespace_or_raise(note.namespace)
    company_id = _company_id()
    existing = await CRMTask.active_by_data_keys(
        "note_markdown_format",
        {"note_id": note_id},
        ns,
        company_id,
    )
    if existing is not None:
        raise ActiveTaskExistsError(
            "note_markdown_format",
            existing.task_id,
            dedup={"note_id": note_id},
        )
    task_id = str(uuid.uuid4())
    row = CRMTask(
        task_id=task_id,
        task_type="note_markdown_format",
        status="pending",
        stage="pending",
        progress_pct=0,
        company_id=company_id,
        namespace=ns,
        user_id=_user_id(),
        data={
            "note_id": note_id,
            "note_name": note.name or "",
        },
    )
    row = await CRMTask.create(row)

    ctx = get_context()
    if ctx is None or ctx.auth_token is None:
        raise ValueError("Request context is required to start note formatting")
    auth_token = ctx.auth_token
    try:
        task = await enqueue(
            CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN,
            note_id=note_id,
            company_id=row.company_id,
            namespace=ns,
            auth_token=auth_token,
            user_id=row.user_id,
            interface_language=ctx.language.value,
            task_id=task_id,
            background_kind="crm_task",
            extra_labels=mock_llm_side_effect_enqueue_labels(
                MOCK_LLM_SIDE_EFFECT_NOTE_MARKDOWN
            ),
        )
        taskiq_id = str(task.task_id)
    except Exception as exc:
        await CRMTask.patch_progress(
            task_id,
            row.company_id,
            status="failed",
            stage="failed",
            error_message=str(exc),
            completed_at=datetime.now(UTC),
        )
        raise

    await CRMTask.patch_progress(
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


async def enqueue_note_markdown_format_task(
    *,
    authz: AuthzService,
    note_id: str,
    company_id: str,
    namespace: str,
) -> bool:
    """Ставит задачу в TaskIQ. Требует активный request context (JWT, user). Возвращает True, если задача поставлена и разослан WS ``started``."""
    task = await begin_note_markdown_format(note_id=note_id)
    logger.info(
        "note_markdown_format_task_started",
        note_id=note_id,
        task_id=task.task_id,
        taskiq_task_id=task.taskiq_task_id,
    )

    entity = await CRMEntity.get(note_id)
    if entity is None:
        logger.warning(
            "note_markdown_format_started_broadcast_note_missing",
            note_id=note_id,
        )
        return False
    note_date_iso = entity.note_date.isoformat() if entity.note_date is not None else None
    await broadcast_crm_note_event(
        company_id=company_id,
        namespace=namespace,
        note_id=note_id,
        note_date_iso=note_date_iso,
        action="updated",
        note=entity,
        authz=authz,
        skip_notification_center=True,
        markdown_format={
            "phase": "started",
            "chunks_done": 0,
            "chunks_total": 0,
        },
    )
    return True


async def schedule_note_markdown_format(
    *,
    authz: AuthzService,
    note_id: str,
    company_id: str,
    namespace: str,
) -> bool:
    settings = get_crm_settings()
    if not settings.note_attachment_markdown_format_enabled:
        return False
    ctx = get_context()
    if ctx is None or not ctx.auth_token:
        logger.warning(
            "note_markdown_format_schedule_skip_no_context",
            note_id=note_id,
        )
        return False
    try:
        return await enqueue_note_markdown_format_task(
            authz=authz,
            note_id=note_id,
            company_id=company_id,
            namespace=namespace,
        )
    except ActiveTaskExistsError:
        logger.info(
            "note_markdown_format_already_running",
            note_id=note_id,
        )
        return False
