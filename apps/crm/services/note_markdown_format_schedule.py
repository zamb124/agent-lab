"""Постановка фоновой задачи форматирования Markdown для заметки (TaskIQ)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.crm.config import get_crm_settings
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event
from apps.crm.services.task_service import ActiveTaskExistsError
from core.context import get_context
from core.logging import get_logger

if TYPE_CHECKING:
    from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
    from apps.crm.db.repositories.entity_repository import EntityRepository
    from apps.crm.services.task_service import TaskService
    from core.db.repositories.company_repository import CompanyRepository

logger = get_logger(__name__)


async def enqueue_note_markdown_format_task(
    *,
    task_service: TaskService,
    entity_repository: EntityRepository,
    company_repository: CompanyRepository,
    access_grant_repository: AccessGrantRepository,
    note_id: str,
    company_id: str,
    namespace: str,
    expected_updated_at_iso: str,
) -> bool:
    """Ставит задачу в TaskIQ. Требует активный request context (JWT, user). Возвращает True, если задача поставлена и разослан WS ``started``."""
    task = await task_service.start_note_markdown_format(
        note_id=note_id,
        expected_updated_at_iso=expected_updated_at_iso,
    )
    logger.info(
        "note_markdown_format_task_started",
        note_id=note_id,
        task_id=task.task_id,
        taskiq_task_id=task.taskiq_task_id,
    )

    entity = await entity_repository.get(note_id)
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
        company_repository=company_repository,
        access_grant_repository=access_grant_repository,
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
    task_service: TaskService,
    entity_repository: EntityRepository,
    company_repository: CompanyRepository,
    access_grant_repository: AccessGrantRepository,
    note_id: str,
    company_id: str,
    namespace: str,
    expected_updated_at_iso: str,
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
            task_service=task_service,
            entity_repository=entity_repository,
            company_repository=company_repository,
            access_grant_repository=access_grant_repository,
            note_id=note_id,
            company_id=company_id,
            namespace=namespace,
            expected_updated_at_iso=expected_updated_at_iso,
        )
    except ActiveTaskExistsError:
        raise
