"""TaskIQ: AI-починка черновика анализа заметки (ветка CRM flow draft_repair)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.container import get_crm_container
from apps.crm.db.repositories.task_repository import CRM_TASK_TERMINAL_STATUSES
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event
from apps.crm.services.crm_task_ws_broadcast import publish_crm_task_snapshot_for_user
from apps.crm_worker.broker import broker
from apps.crm_worker.task_names import CRM_REPAIR_NOTE_ANALYSIS_DRAFT_TASK_NAME
from apps.crm_worker.tasks.daily_summary_tasks import _set_crm_context
from core.logging import get_logger

logger = get_logger(__name__)


async def _broadcast_draft_repair_phase(
    *,
    company_id: str,
    namespace: str,
    note_id: str,
    phase: Literal["started", "failed", "complete"],
    container,
) -> None:
    entity = await container.entity_repository.get(note_id)
    if entity is None:
        logger.warning(
            "draft_repair_broadcast_note_missing",
            note_id=note_id,
            phase=phase,
        )
        return
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
        draft_repair={"phase": phase},
    )


async def _journal_failed(
    *,
    container,
    task_id: Optional[str],
    company_id: str,
    snapshot_user_id: str,
    error_message: str,
) -> None:
    if not task_id:
        return
    repo = container.task_repository
    now = datetime.now(timezone.utc)
    await repo.patch_progress(
        task_id,
        company_id,
        status="failed",
        stage="failed",
        progress_pct=100,
        error_message=error_message,
        completed_at=now,
    )
    await publish_crm_task_snapshot_for_user(
        user_id=snapshot_user_id,
        repo=repo,
        task_id=task_id,
        company_id=company_id,
    )


async def _journal_completed(
    *,
    container,
    task_id: Optional[str],
    company_id: str,
    snapshot_user_id: str,
) -> None:
    if not task_id:
        return
    repo = container.task_repository
    now = datetime.now(timezone.utc)
    await repo.patch_progress(
        task_id,
        company_id,
        status="completed",
        stage="completed",
        progress_pct=100,
        completed_at=now,
    )
    await publish_crm_task_snapshot_for_user(
        user_id=snapshot_user_id,
        repo=repo,
        task_id=task_id,
        company_id=company_id,
    )


@broker.task(task_name=CRM_REPAIR_NOTE_ANALYSIS_DRAFT_TASK_NAME, queue_name="crm")
async def repair_note_analysis_draft_task(
    note_id: str,
    company_id: str,
    namespace: str,
    auth_token: str,
    user_id: str,
    interface_language: str,
    task_id: Optional[str] = None,
) -> dict[str, Any]:
    await _set_crm_context(
        company_id,
        namespace,
        auth_token,
        user_id,
        interface_language=interface_language,
    )
    container = get_crm_container()
    repo = container.task_repository
    snapshot_user_id = user_id

    if task_id:
        row = await repo.get_for_worker(task_id, company_id)
        if row is None:
            raise ValueError(f"CRM task not found: {task_id}")
        if row.status in CRM_TASK_TERMINAL_STATUSES:
            logger.info(
                "crm.worker.repair_note_analysis_draft_skip_terminal",
                task_id=task_id,
                journal_status=row.status,
            )
            return {
                "status": "skipped",
                "reason": "journal_terminal",
                "journal_status": row.status,
                "note_id": note_id,
            }
        snapshot_user_id = row.user_id
        await repo.patch_progress(
            task_id,
            company_id,
            status="running",
            stage="draft_repair",
            progress_pct=50,
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
        await _journal_failed(
            container=container,
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            error_message=msg,
        )
        raise ValueError(msg)
    if entity.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
        msg = "Ожидалась заметка (entity_type=note)"
        await _journal_failed(
            container=container,
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            error_message=msg,
        )
        raise ValueError(msg)
    if entity.company_id != company_id:
        msg = "Заметка принадлежит другой компании"
        await _journal_failed(
            container=container,
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            error_message=msg,
        )
        raise ValueError(msg)

    try:
        updated = await container.entity_service.repair_analysis_draft_via_flow(note_id)
        await _journal_completed(
            container=container,
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
        )
        await _broadcast_draft_repair_phase(
            company_id=company_id,
            namespace=namespace,
            note_id=note_id,
            phase="complete",
            container=container,
        )
        return {"status": "complete", "note_id": note_id, "draft_version": updated.draft_version}
    except Exception as exc:
        msg = str(exc).strip()
        if not msg:
            msg = type(exc).__name__
        await _journal_failed(
            container=container,
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            error_message=msg,
        )
        await _broadcast_draft_repair_phase(
            company_id=company_id,
            namespace=namespace,
            note_id=note_id,
            phase="failed",
            container=container,
        )
        await container.entity_service.record_note_analysis_failure(note_id, msg)
        raise
