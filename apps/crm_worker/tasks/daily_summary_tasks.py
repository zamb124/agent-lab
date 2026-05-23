"""
TaskIQ задачи пересчета Daily Summary для CRM.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, select

import core.tracing.attributes as trace_attributes
from apps.crm.container import get_crm_container
from apps.crm.db.models import CRMEntity, CRMTask
from apps.crm.db.repositories.task_repository import CRM_TASK_TERMINAL_STATUSES
from apps.crm.scheduled_task_constants import CRM_RECONCILE_DAILY_SUMMARY_TASK_NAME
from apps.crm.services.crm_task_ws_broadcast import publish_crm_task_snapshot_for_user
from apps.crm.services.namespace_notification_recipients import (
    normalize_namespace_for_broadcast,
    resolve_user_ids_for_namespace_broadcast,
)
from apps.crm.services.task_service import ALL_NAMESPACES_TASK_KEY
from apps.crm_worker.broker import broker
from apps.crm_worker.task_names import (
    CRM_REBUILD_DAILY_SUMMARY_TASK_NAME,
    CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME,
)
from core.context import Context, set_context
from core.logging import get_logger
from core.models.i18n_models import Language
from core.models.identity_models import User
from core.tracing.operation_span import traced_operation
from core.types import JsonObject
from core.utils.tokens import TokenType, get_token_service
from core.websocket.publisher import Notification, NotificationType, notify_user

if TYPE_CHECKING:
    from apps.crm.container import CRMContainer

logger = get_logger(__name__)

# user_id из set_crm_context без реального пользователя — не искать в user_repository
_WORKER_PLACEHOLDER_USER_IDS = frozenset({"crm-worker"})


async def set_crm_context(
    company_id: str,
    namespace: str | None = None,
    auth_token: str | None = None,
    user_id: str | None = None,
    interface_language: str | None = None,
) -> None:
    if namespace is None:
        normalized_namespace = ""
    else:
        s = str(namespace).strip()
        if not s:
            raise ValueError(
                "namespace: пустая строка недопустима, передайте None если контекст без пространства"
            )
        normalized_namespace = s
    resolved_user_id = user_id or "crm-worker"
    lang = Language(interface_language) if interface_language is not None else Language.RU
    container = get_crm_container()
    company_row = await container.company_repository.get(company_id)
    if company_row is None:
        raise ValueError(f"Company not found for CRM worker context: {company_id}")
    context = Context(
        user=User(user_id=resolved_user_id, name="CRM Worker"),
        active_company=company_row,
        session_id=f"crm-worker:{company_id}",
        channel="taskiq",
        active_namespace=normalized_namespace,
        auth_token=auth_token,
        language=lang,
    )
    set_context(context)


async def _build_auth_token_for_company(company_id: str, user_id: str | None) -> str:
    container = get_crm_container()
    resolved_user_id = user_id
    if resolved_user_id in _WORKER_PLACEHOLDER_USER_IDS:
        resolved_user_id = None
    if not resolved_user_id:
        company = await container.company_repository.get(company_id)
        if company is None:
            raise ValueError(f"Company not found for daily summary rebuild: {company_id}")
        if company.owner_user_id:
            resolved_user_id = company.owner_user_id
        elif company.members:
            member_ids = list(company.members.keys())
            if not member_ids:
                raise ValueError(f"Company has empty members map: {company_id}")
            resolved_user_id = member_ids[0]
        else:
            raise ValueError(f"No owner_user_id/members for company {company_id}")

    user = await container.user_repository.get(resolved_user_id)
    if user is None:
        raise ValueError(f"User not found for daily summary auth token: {resolved_user_id}")

    token_service = get_token_service()
    return token_service.create_token(
        user_id=resolved_user_id,
        company_id=company_id,
        roles=user.companies.get(company_id, []),
        token_type=TokenType.SESSION,
    )


async def _notify_daily_summary_updated(
    company_id: str,
    date_str: str,
    namespace: str | None,
    summary_state: JsonObject,
    *,
    container: "CRMContainer",
) -> None:
    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    recipient_user_ids = await resolve_user_ids_for_namespace_broadcast(
        company_id=company_id,
        namespace=normalized_namespace,
        company_repository=container.company_repository,
        access_grant_repository=container.access_grant_repository,
    )

    notification_data: JsonObject = {
        "event": "crm.daily_summary.updated",
        "company_id": company_id,
        "namespace": normalized_namespace,
        "date": date_str,
        "summary_state": summary_state,
    }
    for user_id in recipient_user_ids:
        await notify_user(
            user_id=user_id,
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
    container: "CRMContainer",
    task_id: str,
    company_id: str,
) -> None:
    repo = container.task_repository
    row = await repo.get_for_worker(task_id, company_id)
    if row is None:
        logger.warning(
            "crm_summary_rebuild_task_row_missing",
            task_id=task_id,
            company_id=company_id,
        )
        return
    await publish_crm_task_snapshot_for_user(
        user_id=row.user_id,
        repo=repo,
        task_id=task_id,
        company_id=company_id,
    )


@broker.task(task_name=CRM_REBUILD_DAILY_SUMMARY_TASK_NAME, queue_name="crm")
async def rebuild_daily_summary_task(
    company_id: str,
    date_str: str,
    namespace: str | None = None,
    reason: str = "event",
    auth_token: str | None = None,
    user_id: str | None = None,
    task_id: str | None = None,
) -> JsonObject:
    """Пересчитывает и сохраняет summary в Redis state.

    task_id — опциональный идентификатор записи CRMTask для обновления прогресса.
    """
    resolved_auth_token = auth_token
    if resolved_auth_token is None:
        resolved_auth_token = await _build_auth_token_for_company(
            company_id=company_id, user_id=user_id
        )
    await set_crm_context(
        company_id=company_id,
        namespace=namespace,
        auth_token=resolved_auth_token,
        user_id=user_id,
    )
    container = get_crm_container()

    if task_id:
        journal = await container.task_repository.get_for_worker(task_id, company_id)
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

        await container.task_repository.patch_progress(
            task_id,
            company_id,
            status="running",
            stage="summarizing_day",
            progress_pct=50,
            started_at=datetime.now(timezone.utc),
        )
        await _snapshot_crm_task_if_present(
            container=container, task_id=task_id, company_id=company_id
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
            state = await container.entity_service.rebuild_daily_summary(
                date_str=date_str,
                namespace=namespace,
            )
    except Exception as exc:
        if task_id:
            await container.task_repository.patch_progress(
                task_id,
                company_id,
                status="failed",
                stage="failed",
                progress_pct=100,
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
            await _snapshot_crm_task_if_present(
                container=container, task_id=task_id, company_id=company_id
            )
        raise

    if task_id:
        await container.task_repository.patch_progress(
            task_id,
            company_id,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
        )
        await _snapshot_crm_task_if_present(
            container=container, task_id=task_id, company_id=company_id
        )

    if state.get("revalidating") is False and state.get("stale") is False:
        await _notify_daily_summary_updated(
            company_id=company_id,
            date_str=date_str,
            namespace=namespace,
            summary_state=state,
            container=container,
        )
    logger.info(f"CRM daily summary rebuilt: company_id={company_id}, namespace={namespace or 'all'}, date={date_str}, reason={reason}")
    return state


@broker.task(task_name=CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME, queue_name="crm")
async def rebuild_period_summary_task(
    company_id: str,
    date_from: str,
    date_to: str,
    namespace: str | None = None,
    reason: str = "event",
    auth_token: str | None = None,
    user_id: str | None = None,
    task_id: str | None = None,
) -> JsonObject:
    """Пересчитывает и сохраняет period summary в Redis и S3."""
    resolved_auth_token = auth_token
    if resolved_auth_token is None:
        resolved_auth_token = await _build_auth_token_for_company(
            company_id=company_id, user_id=user_id
        )
    await set_crm_context(
        company_id=company_id,
        namespace=namespace,
        auth_token=resolved_auth_token,
        user_id=user_id,
    )
    container = get_crm_container()

    if task_id:
        journal = await container.task_repository.get_for_worker(task_id, company_id)
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

        await container.task_repository.patch_progress(
            task_id,
            company_id,
            status="running",
            stage="summarizing_day",
            progress_pct=50,
            started_at=datetime.now(timezone.utc),
        )
        await _snapshot_crm_task_if_present(
            container=container, task_id=task_id, company_id=company_id
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
            state = await container.entity_service.rebuild_period_summary(
                date_from=date_from,
                date_to=date_to,
                namespace=namespace,
            )
    except Exception as exc:
        if task_id:
            await container.task_repository.patch_progress(
                task_id,
                company_id,
                status="failed",
                stage="failed",
                progress_pct=100,
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
            await _snapshot_crm_task_if_present(
                container=container, task_id=task_id, company_id=company_id
            )
        raise

    if task_id:
        await container.task_repository.patch_progress(
            task_id,
            company_id,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
        )
        await _snapshot_crm_task_if_present(
            container=container, task_id=task_id, company_id=company_id
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
            container=container,
        )
    logger.info(f"CRM period summary rebuilt: company_id={company_id}, namespace={namespace or 'all'}, from={date_from}, to={date_to}, reason={reason}")
    return state


@broker.task(task_name=CRM_RECONCILE_DAILY_SUMMARY_TASK_NAME, queue_name="crm")
async def reconcile_daily_summary_task(
    days_back: int = 1,
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> JsonObject:
    """
    Периодическая reconcile-задача.

    Перебирает компании/namespace/даты с заметками за последние N дней
    и ставит пересчет по event-driven пути с дедупликацией.
    """
    _ = company_id
    container = get_crm_container()
    since_date = date.today() - timedelta(days=days_back)

    async with container.crm_db.session() as session:
        stmt = (
            select(
                CRMEntity.company_id,
                CRMEntity.namespace,
                CRMEntity.note_date,
            )
            .distinct()
            .where(
                and_(
                    CRMEntity.entity_type == "note",
                    CRMEntity.note_date.is_not(None),
                    CRMEntity.note_date >= since_date,
                )
            )
        )
        raw_rows: Sequence[tuple[str, str, date | None]] = (
            await session.execute(stmt)
        ).tuples().all()
        rows = [
            (row_company_id, row_namespace, row_note_date)
            for row_company_id, row_namespace, row_note_date in raw_rows
            if row_note_date is not None
        ]

    by_company: dict[str, list[tuple[str, str, date]]] = defaultdict(list)
    for row in rows:
        row_company_id, _, _ = row
        by_company[row_company_id].append(row)

    enqueued_count = 0
    for cid in sorted(by_company.keys()):
        company_rows = by_company[cid]
        tick_id = str(uuid.uuid4())
        tick_started = datetime.now(timezone.utc)
        _ = await container.task_repository.create(
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
            queued = await container.entity_service.enqueue_daily_summary_rebuild(
                date_str=row_note_date.isoformat(),
                namespace=row_namespace,
            )
            if queued:
                enqueued_company += 1
        tick_done = datetime.now(timezone.utc)
        await container.task_repository.patch_progress(
            tick_id,
            cid,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=tick_done,
            data_patch={"enqueued": enqueued_company},
        )
        enqueued_count += enqueued_company

    logger.info(f"CRM daily summary reconcile finished: rows={len(rows)}, enqueued={enqueued_count}, days_back={days_back}, companies={len(by_company)}")
    return {
        "rows": len(rows),
        "enqueued": enqueued_count,
        "days_back": days_back,
        "companies": len(by_company),
    }
