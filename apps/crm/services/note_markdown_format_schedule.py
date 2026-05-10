"""Постановка фоновой задачи форматирования Markdown для заметки (TaskIQ)."""

from __future__ import annotations

from core.context import get_context
from core.logging import get_logger

from apps.crm.config import get_crm_settings

logger = get_logger(__name__)


async def enqueue_note_markdown_format_task(
    *,
    note_id: str,
    company_id: str,
    namespace: str,
    expected_updated_at_iso: str,
) -> None:
    """Ставит задачу в TaskIQ. Требует активный request context (JWT, user)."""
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


async def schedule_note_markdown_format(
    *,
    note_id: str,
    company_id: str,
    namespace: str,
    expected_updated_at_iso: str,
) -> None:
    settings = get_crm_settings()
    if not settings.note_attachment_markdown_format_enabled:
        return
    try:
        await enqueue_note_markdown_format_task(
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
