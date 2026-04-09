"""
Рассылка WS-уведомлений о событиях заметки CRM пользователям namespace.
"""

from __future__ import annotations

from typing import Literal, Optional, TYPE_CHECKING

from apps.crm.services.namespace_notification_recipients import (
    normalize_namespace_for_broadcast,
    resolve_user_ids_for_namespace_broadcast,
)
from core.logging import get_logger
from core.websocket.publisher import Notification, NotificationType, notify_user

if TYPE_CHECKING:
    from core.db.repositories import CompanyRepository
    from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository

logger = get_logger(__name__)

CrmNoteWsAction = Literal["created", "updated", "deleted"]


async def broadcast_crm_note_event(
    company_id: str,
    namespace: str,
    note_id: str,
    note_date_iso: Optional[str],
    action: CrmNoteWsAction,
    *,
    company_repository: "CompanyRepository",
    access_grant_repository: "AccessGrantRepository",
) -> None:
    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    recipient_user_ids = await resolve_user_ids_for_namespace_broadcast(
        company_id=company_id,
        namespace=normalized_namespace,
        company_repository=company_repository,
        access_grant_repository=access_grant_repository,
    )
    notification_data = {
        "event": "crm.note.updated",
        "company_id": company_id,
        "namespace": normalized_namespace,
        "note_id": note_id,
        "note_date": note_date_iso,
        "action": action,
    }
    if action == "created":
        title = "Новая заметка"
        message = "В пространстве появилась заметка"
    elif action == "updated":
        title = "Заметка обновлена"
        message = "Заметка изменена"
    else:
        title = "Заметка удалена"
        message = "Заметка удалена"
    for user_id in recipient_user_ids:
        await notify_user(
            user_id=user_id,
            notification=Notification(
                type=NotificationType.CRM_NOTE_UPDATED,
                title=title,
                message=message,
                service="crm",
                data=notification_data,
            ),
        )
    logger.debug(
        "CRM note WS broadcast: action=%s note_id=%s namespace=%s recipients=%s",
        action,
        note_id,
        normalized_namespace,
        len(recipient_user_ids),
    )
