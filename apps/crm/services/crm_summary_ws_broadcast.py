"""
Рассылка UI-событий о пересчёте сводок CRM пользователям namespace.

Бэкенд публикует `crm/daily_summary/updated` и `crm/period_summary/updated`
в общий канал `platform:ui_events`; фронт получает их через WebSocket и
обновляет соответствующий slice без повторного запроса.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.crm.services.namespace_notification_recipients import (
    normalize_namespace_for_broadcast,
    resolve_user_ids_for_namespace_broadcast,
)
from core.logging import get_logger
from core.ui_events import publish_ui_event_to_user

if TYPE_CHECKING:
    from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
    from core.db.repositories import CompanyRepository

logger = get_logger(__name__)


async def broadcast_crm_daily_summary_updated(
    *,
    company_id: str,
    namespace: str | None,
    date_str: str,
    state: dict[str, Any],
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
    payload = {
        "company_id": company_id,
        "namespace": normalized_namespace,
        "date": date_str,
        "state": state,
    }
    for user_id in recipient_user_ids:
        await publish_ui_event_to_user(
            user_id=user_id,
            type="crm/daily_summary/updated",
            payload=payload,
        )
    logger.debug(
        "CRM daily summary WS broadcast: date=%s namespace=%s recipients=%s",
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
    state: dict[str, Any],
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
    payload = {
        "company_id": company_id,
        "namespace": normalized_namespace,
        "date_from": date_from,
        "date_to": date_to,
        "state": state,
    }
    for user_id in recipient_user_ids:
        await publish_ui_event_to_user(
            user_id=user_id,
            type="crm/period_summary/updated",
            payload=payload,
        )
    logger.debug(
        "CRM period summary WS broadcast: range=%s..%s namespace=%s recipients=%s",
        date_from,
        date_to,
        normalized_namespace,
        len(recipient_user_ids),
    )
