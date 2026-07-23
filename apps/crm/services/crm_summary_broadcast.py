"""Рассылка UI-событий о пересчёте сводок CRM на шину `platform:events`.

Одно событие на факт: `publish_event_to_users` со всеми получателями namespace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.crm.services.crm_realtime_events import (
    CRM_DAILY_SUMMARY_UPDATED,
    CRM_PERIOD_SUMMARY_UPDATED,
)
from apps.crm.services.namespace_notification_recipients import (
    normalize_namespace_for_broadcast,
    resolve_user_ids_for_namespace_broadcast,
)
from core.events import publish_event_to_users
from core.logging import get_logger
from core.types import JsonObject

if TYPE_CHECKING:
    from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
    from core.db.repositories import CompanyRepository

logger = get_logger(__name__)


async def broadcast_crm_daily_summary_updated(
    *,
    company_id: str,
    namespace: str | None,
    date_str: str,
    state: JsonObject,
    company_repository: CompanyRepository,
    access_grant_repository: AccessGrantRepository,
) -> None:
    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    recipient_user_ids = await resolve_user_ids_for_namespace_broadcast(
        company_id=company_id,
        namespace=normalized_namespace,
        company_repository=company_repository,
        access_grant_repository=access_grant_repository,
    )
    payload: JsonObject = {
        "company_id": company_id,
        "namespace": normalized_namespace,
        "date": date_str,
        "state": state,
    }
    if recipient_user_ids:
        await publish_event_to_users(
            recipient_user_ids,
            CRM_DAILY_SUMMARY_UPDATED,
            payload,
            company_id=company_id,
        )
    logger.debug(
        "CRM daily summary platform event: date=%s namespace=%s recipients=%s",
        date_str,
        normalized_namespace,
        len(recipient_user_ids),
    )


async def broadcast_crm_period_summary_updated(
    *,
    company_id: str,
    namespace: str | None,
    date_from: str,
    date_to: str,
    state: JsonObject,
    company_repository: CompanyRepository,
    access_grant_repository: AccessGrantRepository,
) -> None:
    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    recipient_user_ids = await resolve_user_ids_for_namespace_broadcast(
        company_id=company_id,
        namespace=normalized_namespace,
        company_repository=company_repository,
        access_grant_repository=access_grant_repository,
    )
    payload: JsonObject = {
        "company_id": company_id,
        "namespace": normalized_namespace,
        "date_from": date_from,
        "date_to": date_to,
        "state": state,
    }
    if recipient_user_ids:
        await publish_event_to_users(
            recipient_user_ids,
            CRM_PERIOD_SUMMARY_UPDATED,
            payload,
            company_id=company_id,
        )
    logger.debug(
        "CRM period summary platform event: range=%s..%s namespace=%s recipients=%s",
        date_from,
        date_to,
        normalized_namespace,
        len(recipient_user_ids),
    )
