"""Рассылка UI-событий о пересчёте сводок CRM на шину `platform:events`.

Одно событие на факт: ``publish_event_to_company`` (crm_namespace.can_view
включает company#member — ``list_users`` разворачивает весь roster).
"""

from __future__ import annotations

from apps.crm.events import (
    CRM_DAILY_SUMMARY_UPDATED,
    CRM_PERIOD_SUMMARY_UPDATED,
)
from apps.crm.services.namespace_notification_recipients import (
    normalize_namespace_for_broadcast,
)
from core.authz.service import AuthzService
from core.events import publish_event_to_company
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


async def broadcast_crm_daily_summary_updated(
    *,
    company_id: str,
    namespace: str | None,
    date_str: str,
    state: JsonObject,
    authz: AuthzService,
) -> None:
    _ = authz
    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    payload: JsonObject = {
        "company_id": company_id,
        "namespace": normalized_namespace,
        "date": date_str,
        "state": state,
    }
    await publish_event_to_company(
        company_id,
        CRM_DAILY_SUMMARY_UPDATED,
        payload,
    )
    logger.debug(
        "CRM daily summary platform event: date=%s namespace=%s delivery=company",
        date_str,
        normalized_namespace,
    )


async def broadcast_crm_period_summary_updated(
    *,
    company_id: str,
    namespace: str | None,
    date_from: str,
    date_to: str,
    state: JsonObject,
    authz: AuthzService,
) -> None:
    _ = authz
    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    payload: JsonObject = {
        "company_id": company_id,
        "namespace": normalized_namespace,
        "date_from": date_from,
        "date_to": date_to,
        "state": state,
    }
    await publish_event_to_company(
        company_id,
        CRM_PERIOD_SUMMARY_UPDATED,
        payload,
    )
    logger.debug(
        "CRM period summary platform event: range=%s..%s namespace=%s delivery=company",
        date_from,
        date_to,
        normalized_namespace,
    )
