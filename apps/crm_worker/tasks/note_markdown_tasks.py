"""TaskIQ: форматирование description заметки через общий TextTransformService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.container import get_crm_container
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event
from apps.crm.services.crm_task_ws_broadcast import publish_crm_task_snapshot_for_user
from apps.crm_worker.broker import broker
from apps.crm_worker.task_names import CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN_TASK_NAME
from apps.crm_worker.tasks.daily_summary_tasks import set_crm_context
from core.config import get_settings
from core.logging import get_logger
from core.text_transforms import TextTransformService
from core.text_transforms.chunking import split_text_into_markdown_chunks
from core.text_transforms.strip_outer_markdown_fence import strip_outer_markdown_code_fence

logger = get_logger(__name__)


def _normalize_utc_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_expected_updated_at(raw: str) -> datetime:
    s = raw.strip()
    normalized = s.replace("Z", "+00:00") if s.endswith("Z") and "+00:00" not in s else s
    parsed = datetime.fromisoformat(normalized)
    return _normalize_utc_dt(parsed)


async def _journal_terminal_markdown(
    *,
    container,
    task_id: str | None,
    company_id: str,
    snapshot_user_id: str,
    status: str,
    stage: str,
    progress_pct: int,
    error_message: str | None = None,
    data_patch: dict[str, Any] | None = None,
) -> None:
    if not task_id:
        return
    repo = container.task_repository
    now = datetime.now(timezone.utc)
    await repo.patch_progress(
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
        repo=repo,
        task_id=task_id,
        company_id=company_id,
    )


@broker.task(task_name=CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN_TASK_NAME, queue_name="crm")
async def format_note_description_markdown_task(
    note_id: str,
    company_id: str,
    namespace: str,
    auth_token: str,
    user_id: str,
    interface_language: str,
    expected_updated_at_iso: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    Форматирует заметку через общий TextTransformService. По умолчанию это платформенный
    платформенный LLM default-route с candidate/fallback логикой; явный LitServe остаётся
    доступен на уровне TextTransformService/provider override.
    """
    await set_crm_context(company_id, namespace, auth_token, user_id, interface_language=interface_language)
    container = get_crm_container()
    repo = container.task_repository
    snapshot_user_id = user_id

    if task_id:
        row = await repo.get_for_worker(task_id, company_id)
        if row is None:
            raise ValueError(f"CRM task not found: {task_id}")
        snapshot_user_id = row.user_id
        await repo.patch_progress(
            task_id,
            company_id,
            status="running",
            stage="format_markdown",
            progress_pct=25,
            started_at=datetime.now(timezone.utc),
        )
        await publish_crm_task_snapshot_for_user(
            user_id=snapshot_user_id,
            repo=repo,
            task_id=task_id,
            company_id=company_id,
        )

    entity = await container.entity_repository.get(note_id)
    if entity is None:
        msg = f"Заметка не найдена: {note_id}"
        await _journal_terminal_markdown(
            container=container,
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
            container=container,
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="completed",
            stage="skipped_not_note",
            progress_pct=100,
            data_patch={"markdown_format_result": "skipped_not_note"},
        )
        return {"status": "skipped_not_note", "note_id": note_id}

    expected = _parse_expected_updated_at(expected_updated_at_iso)
    current = _normalize_utc_dt(entity.updated_at)
    delta_seconds = abs((current - expected).total_seconds())
    if delta_seconds > 0.05:
        logger.info(
            "note_markdown_format_skip_stale_updated_at",
            note_id=note_id,
            expected=expected.isoformat(),
            current=current.isoformat(),
            delta_seconds=delta_seconds,
        )
        await _journal_terminal_markdown(
            container=container,
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="completed",
            stage="skipped_stale",
            progress_pct=100,
            data_patch={"markdown_format_result": "skipped_stale"},
        )
        return {"status": "skipped_stale", "note_id": note_id}

    if entity.company_id != company_id:
        msg = (
            f"note_markdown_format company mismatch: entity={entity.company_id} task={company_id}"
        )
        await _journal_terminal_markdown(
            container=container,
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
            container=container,
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            status="completed",
            stage="skipped_empty_description",
            progress_pct=100,
            data_patch={"markdown_format_result": "skipped_empty_description"},
        )
        return {"status": "skipped_empty_description", "note_id": note_id}

    chunk_lim = int(get_settings().provider_litserve.infra.markdown_max_chunk_chars)
    chunks_total = len(split_text_into_markdown_chunks(str(desc).strip(), chunk_lim)) or 1
    try:
        markdown_raw = await TextTransformService().format_markdown(
            str(desc).strip(),
            max_chunk_chars=chunk_lim,
        )
    except Exception as exc:
        logger.warning(
            "note_markdown_format_failed",
            note_id=note_id,
            error=str(exc),
        )
        await _journal_terminal_markdown(
            container=container,
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
            container=container,
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

    entity.description = markdown
    entity.updated_at = datetime.now(timezone.utc)
    merged = await container.entity_repository.update(entity)

    await _journal_terminal_markdown(
        container=container,
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
        company_repository=container.company_repository,
        access_grant_repository=container.access_grant_repository,
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
