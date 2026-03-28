"""
TaskIQ задачи пересчета Daily Summary для CRM.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import and_, select

from apps.crm.container import get_crm_container
from apps.crm.db.models import CRMEntity
from apps.crm_worker.broker import broker
from core.context import Context, set_context
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.utils.tokens import TokenType, get_token_service
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


def _set_crm_context(
    company_id: str,
    namespace: Optional[str] = None,
    auth_token: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    normalized_namespace = namespace or "default"
    resolved_user_id = user_id or "crm-worker"
    context = Context(
        user=User(user_id=resolved_user_id, name="CRM Worker"),
        active_company=Company(company_id=company_id, name=company_id),
        session_id=f"crm-worker:{company_id}",
        channel="taskiq",
        active_namespace=normalized_namespace,
        auth_token=auth_token,
    )
    set_context(context)


async def _build_auth_token_for_company(company_id: str, user_id: Optional[str]) -> str:
    container = get_crm_container()
    resolved_user_id = user_id
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


def _normalize_namespace(namespace: Optional[str]) -> str:
    if namespace is None:
        return "all"
    if namespace.strip() == "":
        return "all"
    return namespace


async def _resolve_summary_recipient_user_ids(
    company_id: str,
    namespace: Optional[str],
) -> list[str]:
    container = get_crm_container()
    company = await container.company_repository.get(company_id)
    if company is None:
        raise ValueError(f"Company not found for summary notifications: {company_id}")

    company_user_ids = set(company.members.keys())
    if company.owner_user_id:
        company_user_ids.add(company.owner_user_id)
    if not company_user_ids:
        raise ValueError(f"Company has no members for summary notifications: {company_id}")

    normalized_namespace = _normalize_namespace(namespace)
    recipients: set[str] = set(company_user_ids)
    if normalized_namespace in {"all", "default"}:
        return sorted(recipients)

    grants = await container.access_grant_repository.find_by_resource(
        resource_type="namespace",
        resource_id=normalized_namespace,
        resource_company_id=company_id,
    )
    for grant in grants:
        if grant.grant_type == "public":
            continue
        if grant.grant_type == "user":
            if not grant.target_user_id:
                raise ValueError("Namespace user grant must contain target_user_id")
            recipients.add(grant.target_user_id)
            continue
        if grant.grant_type == "company":
            if not grant.target_company_id:
                raise ValueError("Namespace company grant must contain target_company_id")
            target_company = await container.company_repository.get(grant.target_company_id)
            if target_company is None:
                raise ValueError(
                    f"Target company not found for namespace grant: {grant.target_company_id}"
                )
            recipients.update(target_company.members.keys())
            if target_company.owner_user_id:
                recipients.add(target_company.owner_user_id)
    return sorted(recipients)


async def _notify_daily_summary_updated(
    company_id: str,
    date_str: str,
    namespace: Optional[str],
    summary_state: dict[str, Any],
) -> None:
    normalized_namespace = _normalize_namespace(namespace)
    recipient_user_ids = await _resolve_summary_recipient_user_ids(
        company_id=company_id,
        namespace=normalized_namespace,
    )

    notification_data = {
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
                title="Daily Summary обновлен",
                message=f"Обновлена сводка за {date_str}",
                service="crm",
                data=notification_data,
            ),
        )


@broker.task(task_name="crm_rebuild_daily_summary", queue_name="crm")
async def rebuild_daily_summary_task(
    company_id: str,
    date_str: str,
    namespace: Optional[str] = None,
    reason: str = "event",
    auth_token: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Пересчитывает и сохраняет summary в Redis state."""
    resolved_auth_token = auth_token
    if resolved_auth_token is None:
        resolved_auth_token = await _build_auth_token_for_company(company_id=company_id, user_id=user_id)
    _set_crm_context(
        company_id=company_id,
        namespace=namespace,
        auth_token=resolved_auth_token,
        user_id=user_id,
    )
    container = get_crm_container()
    state = await container.entity_service.rebuild_daily_summary(
        date_str=date_str,
        namespace=namespace,
    )
    if state.get("revalidating") is False and state.get("stale") is False:
        await _notify_daily_summary_updated(
            company_id=company_id,
            date_str=date_str,
            namespace=namespace,
            summary_state=state,
        )
    logger.info(
        "CRM daily summary rebuilt: "
        f"company_id={company_id}, namespace={namespace or 'all'}, date={date_str}, reason={reason}"
    )
    return state


@broker.task(task_name="crm_reconcile_daily_summary", queue_name="crm")
async def reconcile_daily_summary_task(days_back: int = 1) -> dict[str, Any]:
    """
    Периодическая reconcile-задача.

    Перебирает компании/namespace/даты с заметками за последние N дней
    и ставит пересчет по event-driven пути с дедупликацией.
    """
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
        rows = (await session.execute(stmt)).all()

    enqueued_count = 0
    for row in rows:
        company_id = row.company_id
        namespace = row.namespace
        note_date = row.note_date
        _set_crm_context(company_id=company_id, namespace=namespace)
        queued = await container.entity_service.enqueue_daily_summary_rebuild(
            date_str=note_date.isoformat(),
            namespace=namespace,
        )
        if queued:
            enqueued_count += 1

    logger.info(
        f"CRM daily summary reconcile finished: rows={len(rows)}, enqueued={enqueued_count}, days_back={days_back}"
    )
    return {
        "rows": len(rows),
        "enqueued": enqueued_count,
        "days_back": days_back,
    }
