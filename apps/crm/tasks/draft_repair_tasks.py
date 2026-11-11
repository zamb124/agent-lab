"""TaskIQ: AI-починка черновика анализа заметки (ветка CRM flow draft_repair)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.di import Di
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.task import CRM_TASK_TERMINAL_STATUSES, CRMTask
from apps.crm.services.crm_note_broadcast import broadcast_crm_note_event
from apps.crm.services.crm_task_broadcast import publish_crm_task_snapshot_for_user
from apps.crm.tasks.crm_context import set_crm_context
from apps.crm.tasks.task_names import CRM_REPAIR_NOTE_ANALYSIS_DRAFT
from core.a2a.submit import A2ACallPending, set_a2a_resume_context
from core.logging import get_logger
from core.tasks import platform_task
from core.types import JsonObject

logger = get_logger(__name__)


async def _broadcast_draft_repair_phase(
    *,
    company_id: str,
    namespace: str,
    note_id: str,
    phase: Literal["started", "failed", "complete"],
    di: Di,
) -> None:
    entity = await CRMEntity.get(note_id)
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
        note=entity,
        authz=di.authz_service,
        skip_notification_center=True,
        draft_repair={"phase": phase},
    )


async def _journal_failed(
    *,
    task_id: str | None,
    company_id: str,
    snapshot_user_id: str,
    error_message: str,
) -> None:
    if not task_id:
        return
    now = datetime.now(timezone.utc)
    await CRMTask.patch_progress(
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
        task_id=task_id,
        company_id=company_id,
    )


async def _journal_completed(
    *,
    task_id: str | None,
    company_id: str,
    snapshot_user_id: str,
) -> None:
    if not task_id:
        return
    now = datetime.now(timezone.utc)
    await CRMTask.patch_progress(
        task_id,
        company_id,
        status="completed",
        stage="completed",
        progress_pct=100,
        completed_at=now,
    )
    await publish_crm_task_snapshot_for_user(
        user_id=snapshot_user_id,
        task_id=task_id,
        company_id=company_id,
    )


@platform_task(CRM_REPAIR_NOTE_ANALYSIS_DRAFT)
async def repair_note_analysis_draft_task(
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
    await set_crm_context(
        company_id,
        namespace,
        auth_token,
        user_id,
        interface_language=interface_language,
    )
    _ = set_a2a_resume_context(
        CRM_REPAIR_NOTE_ANALYSIS_DRAFT.name,
        {
            "note_id": note_id,
            "company_id": company_id,
            "namespace": namespace,
            "auth_token": auth_token,
            "user_id": user_id,
            "interface_language": interface_language,
            "task_id": task_id,
        },
        run_nonce=task_id or note_id,
    )
    snapshot_user_id = user_id

    if task_id:
        row = await CRMTask.by_company_and_task_id(company_id, task_id)
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
        await CRMTask.patch_progress(
            task_id,
            company_id,
            status="running",
            stage="draft_repair",
            progress_pct=50,
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
        await _journal_failed(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            error_message=msg,
        )
        raise ValueError(msg)
    if entity.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
        msg = "Ожидалась заметка (entity_type=note)"
        await _journal_failed(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            error_message=msg,
        )
        raise ValueError(msg)
    if entity.company_id != company_id:
        msg = "Заметка принадлежит другой компании"
        await _journal_failed(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
            error_message=msg,
        )
        raise ValueError(msg)

    try:
        updated = await di.entity_service.repair_analysis_draft_via_flow(note_id)
        await _journal_completed(
            task_id=task_id,
            company_id=company_id,
            snapshot_user_id=snapshot_user_id,
        )
        await _broadcast_draft_repair_phase(
            company_id=company_id,
            namespace=namespace,
            note_id=note_id,
            phase="complete",
            di=di,
        )
        return {"status": "complete", "note_id": note_id, "draft_version": updated.draft_version}
    except A2ACallPending:
        if task_id:
            await CRMTask.patch_progress(
                task_id,
                company_id,
                status="running",
                stage="waiting_ai",
                progress_pct=60,
            )
            await publish_crm_task_snapshot_for_user(
                user_id=snapshot_user_id,
                task_id=task_id,
                company_id=company_id,
            )
        logger.info("crm.draft_repair.a2a_parked", task_id=task_id, note_id=note_id)
        return {"status": "waiting_ai", "note_id": note_id}
    except Exception as exc:
        msg = str(exc).strip()
        if not msg:
            msg = type(exc).__name__
        await _journal_failed(
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
            di=di,
        )
        await di.entity_service.record_note_analysis_failure(note_id, msg)
        raise
