"""Постановка фоновой задачи форматирования Markdown для заметки (TaskIQ)."""

from __future__ import annotations

from core.context import get_context
from core.logging import get_logger

from apps.crm.config import get_crm_settings
from apps.crm.container import get_crm_container
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event

logger = get_logger(__name__)


async def enqueue_note_markdown_format_task(
    *,
    note_id: str,
    company_id: str,
    namespace: str,
    expected_updated_at_iso: str,
) -> bool:
    """Ставит задачу в TaskIQ. Требует активный request context (JWT, user). Возвращает True, если задача поставлена и разослан WS ``started``."""
    ctx = get_context()
    if ctx is None or not ctx.auth_token or ctx.user is None:
        raise ValueError("note_markdown_format: нет контекста запроса (user/auth_token)")

    from apps.crm_worker.tasks.note_markdown_tasks import format_note_description_markdown_task

    await format_note_description_markdown_task.kiq(
        note_id=note_id,
        company_id=company_id,
        namespace=namespace,
        auth_token=ctx.auth_token,
        user_id=ctx.user.user_id,
        interface_language=ctx.language.value,
        expected_updated_at_iso=expected_updated_at_iso,
    )

    container = get_crm_container()
    entity = await container.entity_repository.get(note_id)
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
        company_repository=container.company_repository,
        access_grant_repository=container.access_grant_repository,
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
    note_id: str,
    company_id: str,
    namespace: str,
    expected_updated_at_iso: str,
) -> bool:
    settings = get_crm_settings()
    if not settings.note_attachment_markdown_format_enabled:
        return False
    try:
        return await enqueue_note_markdown_format_task(
            note_id=note_id,
            company_id=company_id,
            namespace=namespace,
            expected_updated_at_iso=expected_updated_at_iso,
        )
    except ValueError:
        logger.warning(
            "note_markdown_format_schedule_skip_no_context",
            note_id=note_id,
        )
        return False
