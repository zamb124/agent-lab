"""TaskIQ: форматирование description заметки через общий TextTransformService."""

from __future__ import annotations

from datetime import datetime, timezone

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.di import Di
from apps.crm.models.crm_entity import CRMEntity, index_crm_entity
from apps.crm.models.task import CRMTask
from apps.crm.services.crm_note_broadcast import broadcast_crm_note_event
from apps.crm.services.crm_task_broadcast import publish_crm_task_snapshot_for_user
from apps.crm.tasks.crm_context import set_crm_context
from apps.crm.tasks.task_names import CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN
from core.config import get_settings
from core.logging import get_logger
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.tasks import platform_task
from core.text_transforms import TextTransformService
from core.text_transforms.chunking import split_text_into_markdown_chunks
from core.text_transforms.strip_outer_markdown_fence import strip_outer_markdown_code_fence
from core.types import JsonObject

logger = get_logger(__name__)


async def _journal_terminal_markdown(
    *,
    task_id: str | None,
    company_id: str,
    snapshot_user_id: str,
    status: str,
    stage: str,
    progress_pct: int,
    error_message: str | None = None,
    data_patch: JsonObject | None = None,
) -> None:
    if not task_id:
        return
    now = datetime.now(timezone.utc)
    await CRMTask.patch_progress(
        task_id,
        company_id,
        status=status,
        stage=stage,
        progress_pct=progress_pct,
        completed_at=now,
        error_message=error_message,
        data_patch=data_patch,
    )
    await publish_crm_task_snapshot_for_user(
        user_id=snapshot_user_id,
        task_id=task_id,
        company_id=company_id,
    )


@platform_task(CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN)
async def format_note_description_markdown_task(
    note_id: str,
    company_id: str,
    namespace: str,
    auth_token: str,
    user_id: str,
    interface_language: str,
    task_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """
    Форматирует заметку через общий TextTransformService. Модель выбирается через
    company capability ``llm_format_markdown`` с платформенным humanitec_llm default-route.
    """
    await set_crm_context(company_id, namespace, auth_token, user_id, interface_language=interface_language)
    snapshot_user_id = user_id

    if task_id:
        row = await CRMTask.by_company_and_task_id(company_id, task_id)
        if row is None:
            raise ValueError(f"CRM task not found: {task_id}")
        snapshot_user_id = row.user_id
        await CRMTask.patch_progress(
            task_id,
            company_id,
            status="running",
            stage="format_markdown",
            progress_pct=25,
            started_at=datetime.now(timezone.utc),
        )
        await publish_crm_task_snapshot_for_user(
            user_id=snapshot_user_id,
            task_id=task_id,
            company_id=company_id,
        )

    entity = await CRMEntity.get(note_id)
    if entity is None:
        msg = f"Заметка не найдена: {note_id}"
        await _journal_terminal_markdown(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            error_message=msg,
        )
        raise ValueError(msg)
    if entity.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
        await _journal_terminal_markdown(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="completed",
            stage="skipped_not_note",
            progress_pct=100,
            data_patch={"markdown_format_result": "skipped_not_note"},
        )
        return {"status": "skipped_not_note", "note_id": note_id}

    if entity.company_id != company_id:
        msg = (
            f"note_markdown_format company mismatch: entity={entity.company_id} task={company_id}"
        )
        await _journal_terminal_markdown(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            error_message=msg,
        )
        raise ValueError(msg)

    desc = entity.description
    if desc is None or not str(desc).strip():
        await _journal_terminal_markdown(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="completed",
            stage="skipped_empty_description",
            progress_pct=100,
            data_patch={"markdown_format_result": "skipped_empty_description"},
        )
        return {"status": "skipped_empty_description", "note_id": note_id}

    chunk_lim = int(get_settings().text_transforms.markdown_max_chunk_chars)
    chunks_total = len(split_text_into_markdown_chunks(str(desc).strip(), chunk_lim)) or 1
    try:
        markdown_raw = await TextTransformService().format_markdown(str(desc).strip())
    except Exception as exc:
        logger.warning(
            "note_markdown_format_failed",
            note_id=note_id,
            error=str(exc),
        )
        await _journal_terminal_markdown(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            error_message=str(exc),
        )
        raise

    markdown = strip_outer_markdown_code_fence(markdown_raw.strip())
    if not markdown:
        msg = "note_markdown_format: пустой markdown"
        await _journal_terminal_markdown(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            error_message=msg,
        )
        raise ValueError(msg)

    chunks_processed = chunks_total
    original_description = str(desc)
    merged = await CRMEntity.update_description_if_current(
        note_id,
        expected_description=original_description,
        description=markdown,
    )
    if merged is None:
        logger.info(
            "note_markdown_format_skip_stale_description",
            note_id=note_id,
        )
        await _journal_terminal_markdown(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="completed",
            stage="skipped_stale",
            progress_pct=100,
            data_patch={"markdown_format_result": "skipped_stale"},
        )
        return {"status": "skipped_stale", "note_id": note_id}

    await index_crm_entity(
        get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
        merged,
        replace=True,
    )
    await _journal_terminal_markdown(
        task_id=task_id,
        company_id=company_id,
        snapshot_user_id=snapshot_user_id,
        status="completed",
        stage="completed",
        progress_pct=100,
        data_patch={
            "markdown_format_result": "completed",
            "chunks_total": chunks_total,
            "chunks_processed": chunks_processed,
        },
    )

    note_date_iso = merged.note_date.isoformat() if merged.note_date is not None else None
    await broadcast_crm_note_event(
        company_id=merged.company_id,
        namespace=merged.namespace,
        note_id=merged.entity_id,
        note_date_iso=note_date_iso,
        action="updated",
        note=merged,
        authz=di.authz_service,
        skip_notification_center=False,
        markdown_format={
            "phase": "complete",
            "chunks_done": chunks_processed,
            "chunks_total": chunks_total,
        },
    )

    return {
        "status": "completed",
        "note_id": note_id,
        "chunks_total": chunks_total,
        "chunks_processed": chunks_processed,
    }
