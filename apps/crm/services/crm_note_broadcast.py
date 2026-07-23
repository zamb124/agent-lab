"""Рассылка realtime-событий CRM note на шину `platform:events`.

Публикует **два** типа на один факт (разная семантика):

1. ``notify/crm/crm_note_updated_received`` через ``notify_user`` — toast /
   notification-center + offline web-push.
2. ``crm/note/updated`` — одно доменное push-событие с ``delivery.user_ids``
   для slice ``crm/notes_list`` (snapshot ``note`` при create/update;
   при delete — только ``note_id`` + ``action``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

from apps.crm.db.models import CRMEntity
from apps.crm.models.api import EntityResponse
from apps.crm.services.crm_realtime_events import CRM_NOTE_UPDATED
from apps.crm.services.namespace_notification_recipients import (
    normalize_namespace_for_broadcast,
    resolve_user_ids_for_namespace_broadcast,
)
from core.events import publish_event_to_users
from core.logging import get_logger
from core.types import JsonObject, require_json_object
from core.websocket.publisher import Notification, NotificationType, notify_user

if TYPE_CHECKING:
    from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
    from core.db.repositories import CompanyRepository

logger = get_logger(__name__)

CrmNoteAction = Literal["created", "updated", "deleted"]


class MarkdownFormatProgressPayload(TypedDict):
    """Дополнение payload ``crm/note/updated`` при format_markdown."""

    phase: Literal["started", "partial", "complete"]
    chunks_done: int
    chunks_total: int


class DraftRepairProgressPayload(TypedDict):
    """Дополнение payload при AI-починке черновика анализа."""

    phase: Literal["started", "failed", "complete"]


def _note_snapshot(note: CRMEntity) -> JsonObject:
    return EntityResponse.model_validate(note).model_dump(mode="json")


async def broadcast_crm_note_event(
    company_id: str,
    namespace: str,
    note_id: str,
    note_date_iso: str | None,
    action: CrmNoteAction,
    *,
    company_repository: CompanyRepository,
    access_grant_repository: AccessGrantRepository,
    note: CRMEntity | None = None,
    skip_notification_center: bool = False,
    markdown_format: MarkdownFormatProgressPayload | None = None,
    draft_repair: DraftRepairProgressPayload | None = None,
) -> None:
    if action == "deleted":
        if note is not None:
            raise ValueError("broadcast_crm_note_event: note must be None when action=deleted")
    elif note is None:
        raise ValueError(f"broadcast_crm_note_event: note required when action={action}")
    elif note.entity_id != note_id:
        raise ValueError(
            f"broadcast_crm_note_event: note.entity_id={note.entity_id} != note_id={note_id}"
        )

    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    recipient_user_ids = await resolve_user_ids_for_namespace_broadcast(
        company_id=company_id,
        namespace=normalized_namespace,
        company_repository=company_repository,
        access_grant_repository=access_grant_repository,
    )
    notification_data: JsonObject = {
        "event": "crm/note/updated",
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
    domain_event_payload: JsonObject = {
        "company_id": company_id,
        "namespace": normalized_namespace,
        "note_id": note_id,
        "note_date": note_date_iso,
        "action": action,
    }
    if note is not None:
        domain_event_payload["note"] = _note_snapshot(note)
    if markdown_format is not None:
        domain_event_payload["markdown_format"] = require_json_object(
            markdown_format,
            "crm_note_broadcast.markdown_format",
        )
    if draft_repair is not None:
        domain_event_payload["draft_repair"] = require_json_object(
            draft_repair,
            "crm_note_broadcast.draft_repair",
        )
    if not skip_notification_center:
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
    if recipient_user_ids:
        await publish_event_to_users(
            recipient_user_ids,
            CRM_NOTE_UPDATED,
            domain_event_payload,
            company_id=company_id,
        )
    logger.debug(
        "CRM note broadcast: action=%s note_id=%s namespace=%s recipients=%s",
        action,
        note_id,
        normalized_namespace,
        len(recipient_user_ids),
    )
