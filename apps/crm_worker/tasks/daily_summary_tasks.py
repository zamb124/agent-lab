"""
TaskIQ задачи пересчета Daily Summary для CRM.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import core.tracing.attributes as trace_attributes
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.task import CRM_TASK_TERMINAL_STATUSES, CRMTask
from apps.crm.services.crm_summary_broadcast import broadcast_crm_daily_summary_updated
from apps.crm.services.crm_task_broadcast import publish_crm_task_snapshot_for_user
from apps.crm.services.namespace_notification_recipients import (
    normalize_namespace_for_broadcast,
)
from apps.crm.services.task_service import ALL_NAMESPACES_TASK_KEY
from apps.crm_worker.di import Di
from apps.crm_worker.tasks.crm_context import (
    build_auth_token_for_company,
    set_crm_context,
)
from apps.crm_worker.tasks.task_names import (
    CRM_REBUILD_DAILY_SUMMARY,
    CRM_REBUILD_PERIOD_SUMMARY,
    CRM_RECONCILE_DAILY_SUMMARY,
)
from core.logging import get_logger
from core.tasks import platform_task
from core.tracing.operation_span import traced_operation
from core.types import JsonObject
from core.websocket.publisher import Notification, NotificationType, notify_company

logger = get_logger(__name__)


async def _notify_daily_summary_updated(
    company_id: str,
    date_str: str,
    namespace: str | None,
    summary_state: JsonObject,
    *,
    di: Di,
) -> None:
    await broadcast_crm_daily_summary_updated(
        company_id=company_id,
        namespace=namespace,
        date_str=date_str,
        state=summary_state,
        authz=di.authz_service,
    )
    normalized_namespace = normalize_namespace_for_broadcast(namespace)

    notification_data: JsonObject = {
        "event": "crm/daily_summary/updated",
        "company_id": company_id,
        "namespace": normalized_namespace,
        "date": date_str,
        "summary_state": summary_state,
    }
    await notify_company(
        company_id=company_id,
        notification=Notification(
            type=NotificationType.CRM_DAILY_SUMMARY_UPDATED,
            title="Daily Summary обновлён",
            title_i18n_key="crm:notifications.daily_summary_updated_title",
            message=f"Обновлена сводка за {date_str}",
            message_i18n_key="crm:notifications.daily_summary_updated_message",
            message_i18n_vars={"date": date_str},
            service="crm",
            action_url="/crm/notes",
            action_label_i18n_key="crm:notifications.open_crm",
            data=notification_data,
        ),
    )


async def _snapshot_crm_task_if_present(
    *,
    task_id: str,
    company_id: str,
) -> None:
    row = await CRMTask.by_company_and_task_id(company_id, task_id)
    if row is None:
        logger.warning(
            "crm_summary_rebuild_task_row_missing",
            task_id=task_id,
            company_id=company_id,
        )
        return
    await publish_crm_task_snapshot_for_user(
        user_id=row.user_id,
        task_id=task_id,
        company_id=company_id,
    )


@platform_task(CRM_REBUILD_DAILY_SUMMARY)
async def rebuild_daily_summary_task(
    company_id: str,
    date_str: str,
    namespace: str | None = None,
    reason: str = "event",
    auth_token: str | None = None,
    user_id: str | None = None,
    task_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Пересчитывает и сохраняет summary в Redis state.

    task_id — опциональный идентификатор записи CRMTask для обновления прогресса.
    """
    resolved_auth_token = auth_token
    if resolved_auth_token is None:
        resolved_auth_token = await build_auth_token_for_company(
            company_id=company_id, user_id=user_id, authz=di.authz_service
        )
    await set_crm_context(
        company_id=company_id,
        namespace=namespace,
        auth_token=resolved_auth_token,
        user_id=user_id,
    )
    if task_id:
        journal = await CRMTask.by_company_and_task_id(company_id, task_id)
        if journal is None:
            raise ValueError(f"CRM task not found: {task_id}")
        if journal.status in CRM_TASK_TERMINAL_STATUSES:
            logger.info(
                "crm.worker.rebuild_daily_summary_skip_terminal",
                task_id=task_id,
                journal_status=journal.status,
                company_id=company_id,
            )
            return {"skipped": True, "journal_status": journal.status, "task_id": task_id}

        await CRMTask.patch_progress(
            task_id,
            company_id,
            status="running",
            stage="summarizing_day",
            progress_pct=50,
            started_at=datetime.now(timezone.utc),
        )
        await _snapshot_crm_task_if_present(
            task_id=task_id, company_id=company_id
        )

    try:
        async with traced_operation(
            "crm.worker.rebuild_daily_summary",
            event_type="crm.worker",
            operation_category="sync_command",
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                "platform.crm.summary_date": date_str,
                "platform.crm.summary_namespace": namespace or "",
            },
        ):
            state = await di.entity_service.rebuild_daily_summary(
                date_str=date_str,
                namespace=namespace,
            )
    except Exception as exc:
        if task_id:
            await CRMTask.patch_progress(
                task_id,
                company_id,
                status="failed",
                stage="failed",
                progress_pct=100,
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
            await _snapshot_crm_task_if_present(
                task_id=task_id, company_id=company_id
            )
        raise

    if task_id:
        await CRMTask.patch_progress(
            task_id,
            company_id,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
        )
        await _snapshot_crm_task_if_present(
            task_id=task_id, company_id=company_id
        )

    if state.get("revalidating") is False and state.get("stale") is False:
        await _notify_daily_summary_updated(
            company_id=company_id,
            date_str=date_str,
            namespace=namespace,
            summary_state=state,
            di=di,
        )
    logger.info("crm.summary.daily_rebuilt", company_id=company_id, namespace=namespace, date=date_str, reason=reason)
    return state


@platform_task(CRM_REBUILD_PERIOD_SUMMARY)
async def rebuild_period_summary_task(
    company_id: str,
    date_from: str,
    date_to: str,
    namespace: str | None = None,
    reason: str = "event",
    auth_token: str | None = None,
    user_id: str | None = None,
    task_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Пересчитывает и сохраняет period summary в Redis и S3."""
    resolved_auth_token = auth_token
    if resolved_auth_token is None:
        resolved_auth_token = await build_auth_token_for_company(
            company_id=company_id, user_id=user_id, authz=di.authz_service
        )
    await set_crm_context(
        company_id=company_id,
        namespace=namespace,
        auth_token=resolved_auth_token,
        user_id=user_id,
    )
    if task_id:
        journal = await CRMTask.by_company_and_task_id(company_id, task_id)
        if journal is None:
            raise ValueError(f"CRM task not found: {task_id}")
        if journal.status in CRM_TASK_TERMINAL_STATUSES:
            logger.info(
                "crm.worker.rebuild_period_summary_skip_terminal",
                task_id=task_id,
                journal_status=journal.status,
                company_id=company_id,
            )
            return {"skipped": True, "journal_status": journal.status, "task_id": task_id}

        await CRMTask.patch_progress(
            task_id,
            company_id,
            status="running",
            stage="summarizing_day",
            progress_pct=50,
            started_at=datetime.now(timezone.utc),
        )
        await _snapshot_crm_task_if_present(
            task_id=task_id, company_id=company_id
        )

    try:
        async with traced_operation(
            "crm.worker.rebuild_period_summary",
            event_type="crm.worker",
            operation_category="sync_command",
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                "platform.crm.period_from": date_from,
                "platform.crm.period_to": date_to,
            },
        ):
            state = await di.entity_service.rebuild_period_summary(
                date_from=date_from,
                date_to=date_to,
                namespace=namespace,
            )
    except Exception as exc:
        if task_id:
            await CRMTask.patch_progress(
                task_id,
                company_id,
                status="failed",
                stage="failed",
                progress_pct=100,
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
            await _snapshot_crm_task_if_present(
                task_id=task_id, company_id=company_id
            )
        raise

    if task_id:
        await CRMTask.patch_progress(
            task_id,
            company_id,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
        )
        await _snapshot_crm_task_if_present(
            task_id=task_id, company_id=company_id
        )

    if state.get("revalidating") is False and state.get("stale") is False:
        await _notify_daily_summary_updated(
            company_id=company_id,
            date_str=date_from,
            namespace=namespace,
            summary_state={
                "period": True,
                "date_from": date_from,
                "date_to": date_to,
                "summary": state.get("summary", ""),
                "entities": state.get("entities", []),
                "generated_at": state.get("generated_at"),
            },
            di=di,
        )
    logger.info("crm.summary.period_rebuilt", company_id=company_id, namespace=namespace, date_from=date_from, date_to=date_to, reason=reason)
    return state


@platform_task(CRM_RECONCILE_DAILY_SUMMARY)
async def reconcile_daily_summary_task(
    days_back: int = 1,
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """
    Периодическая reconcile-задача.

    Перебирает компании/namespace/даты с заметками за последние N дней
    и ставит пересчет по event-driven пути с дедупликацией.
    """
    _ = company_id
    since_date = date.today() - timedelta(days=days_back)

    distinct_company_ids = await CRMEntity.distinct_note_company_ids_since(since_date)

    enqueued_count = 0
    total_rows_processed = 0
    for cid in distinct_company_ids:
        company_rows = await CRMEntity.distinct_note_scopes_since(since_date, cid)

        total_rows_processed += len(company_rows)
        tick_id = str(uuid.uuid4())
        tick_started = datetime.now(timezone.utc)
        _ = await CRMTask.create(
            CRMTask(
                task_id=tick_id,
                task_type="reconcile_daily_summary_tick",
                status="running",
                stage="running",
                progress_pct=10,
                company_id=cid,
                namespace=ALL_NAMESPACES_TASK_KEY,
                user_id="system",
                data={
                    "schedule_task_id": schedule_task_id,
                    "days_back": days_back,
                    "distinct_note_day_rows": len(company_rows),
                    "enqueued": 0,
                },
                started_at=tick_started,
            )
        )
        enqueued_company = 0
        for row_company_id, row_namespace, row_note_date in company_rows:
            await set_crm_context(company_id=row_company_id, namespace=row_namespace)
            queued = await di.entity_service.enqueue_daily_summary_rebuild(
                date_str=row_note_date.isoformat(),
                namespace=row_namespace,
            )
            if queued:
                enqueued_company += 1
        tick_done = datetime.now(timezone.utc)
        await CRMTask.patch_progress(
            tick_id,
            cid,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=tick_done,
            data_patch={"enqueued": enqueued_company},
        )
        enqueued_count += enqueued_company

    logger.info(
        "crm.daily_summary.reconcile_finished",
        rows=total_rows_processed,
        enqueued=enqueued_count,
        days_back=days_back,
        companies=len(distinct_company_ids),
    )
    return {
        "rows": total_rows_processed,
        "enqueued": enqueued_count,
        "days_back": days_back,
        "companies": len(distinct_company_ids),
    }
