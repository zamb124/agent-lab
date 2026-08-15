"""
Публикация уведомлений пользователям.

Чисто event-driven: каждый сервис формирует доменное событие через
`publish_event_to_user(user_id, type, payload, ...)` (см.
`core/events/publisher.py`). Этот модуль предоставляет тонкий
адаптер `notify_user(...)`, который дополнительно умеет доставить
push-уведомление при offline-пользователе.

Тип события собирается как `notify/<service>/<kind>_received`, где
service — имя бэкенд-сервиса источника (crm/sync/office/...), kind —
конкретный подтип (note_updated, message_received и т.п.). Имя
соответствует контракту `<scope>/<entity>/<verb>`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from core.events import (
    assert_platform_event_type,
    publish_event_to_company,
    publish_event_to_user,
)
from core.logging import get_logger
from core.push.delivery import deliver_offline_push
from core.types import JsonArray, JsonObject, parse_json_object
from core.websocket.manager import notification_manager

logger = get_logger(__name__)


class NotificationType(StrEnum):
    ACCESS_REQUEST = "access_request"
    ENTITY_UPDATED = "entity_updated"
    TASK_COMPLETED = "task_completed"
    MENTION = "mention"
    SYSTEM = "system"
    SYNC_NEW_MESSAGE = "sync_new_message"
    CRM_DAILY_SUMMARY_UPDATED = "crm_daily_summary_updated"
    CRM_NOTE_UPDATED = "crm_note_updated"
    CRM_TASK_UPDATED = "crm_task_updated"
    CALENDAR_NEW_EVENT = "calendar_new_event"
    CALENDAR_SYNC_MEETING_REMINDER = "calendar_sync_meeting_reminder"
    MAIL_NEW_MESSAGE = "mail_new_message"
    OFFICE_DOCUMENT_SAVED = "office_document_saved"
    WORK_ITEM_ASSIGNED = "work_item_assigned"
    WORK_ITEM_UPDATED = "work_item_updated"
    WORK_ITEM_COMMENT = "work_item_comment"


class NotificationAction(BaseModel):
    """Структурированная ссылка/действие внутри уведомления."""

    label: str = ""
    url: str
    label_i18n_key: str | None = None
    label_i18n_vars: JsonObject = Field(default_factory=dict)
    data: JsonObject = Field(default_factory=dict)


class Notification(BaseModel):
    """Уведомление для пользователя — `PlatformEvent(notify/…)` + опционально Web Push."""

    type: NotificationType
    title: str
    message: str
    title_i18n_key: str | None = None
    title_i18n_vars: JsonObject = Field(default_factory=dict)
    message_i18n_key: str | None = None
    message_i18n_vars: JsonObject = Field(default_factory=dict)
    data: JsonObject = Field(default_factory=dict)
    service: str
    priority: str = "normal"
    action_url: str | None = None
    action_label: str | None = None
    action_label_i18n_key: str | None = None
    actions: list[NotificationAction] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _event_type_for(notification: Notification) -> str:
    candidate = f"notify/{notification.service}/{notification.type.value}_received"
    return assert_platform_event_type(candidate)


def _notification_payload(notification: Notification) -> JsonObject:
    actions_payload: JsonArray = [
        parse_json_object(action.model_dump_json(), "NotificationAction")
        for action in notification.actions
    ]
    return {
        "title": notification.title,
        "message": notification.message,
        "title_i18n_key": notification.title_i18n_key,
        "title_i18n_vars": notification.title_i18n_vars,
        "message_i18n_key": notification.message_i18n_key,
        "message_i18n_vars": notification.message_i18n_vars,
        "data": notification.data,
        "priority": notification.priority,
        "action_url": notification.action_url,
        "action_label": notification.action_label,
        "action_label_i18n_key": notification.action_label_i18n_key,
        "actions": actions_payload,
        "created_at": notification.created_at.isoformat(),
        "service": notification.service,
        "kind": notification.type.value,
    }


async def notify_user(user_id: str, notification: Notification) -> None:
    """
    Доставить уведомление пользователю.

    1. Публикуется как событие шины `platform:events` с UI-доставкой
       пользователю — фронт получает его через WebSocket и обрабатывает
       в EventBus.
    2. Если пользователь offline — отправляется Web Push / APNs через
       `deliver_offline_push`.
    """
    event_type = _event_type_for(notification)
    payload = _notification_payload(notification)
    await publish_event_to_user(user_id, event_type, payload)
    logger.info(
        "Notification published: user=%s service=%s kind=%s",
        user_id,
        notification.service,
        notification.type.value,
    )

    if not notification_manager.is_user_connected(user_id):
        _ = await deliver_offline_push(
            user_id,
            title=notification.title,
            message=notification.message,
            action_url=notification.action_url,
            tag=notification.type.value,
            priority=notification.priority,
            data=notification.data,
        )


async def notify_company(company_id: str, notification: Notification) -> None:
    """
    Доставить уведомление всем сокетам компании (без offline-push fanout).

    Используется когда FGA relation раскрывается в весь roster (`company#member`):
    ``list_users`` + per-user ``notify_user`` даёт deadline_exceeded / зависания.
    """
    if not company_id.strip():
        raise ValueError("notify_company: company_id is required")
    event_type = _event_type_for(notification)
    payload = _notification_payload(notification)
    await publish_event_to_company(company_id, event_type, payload)
    logger.info(
        "Notification published: company=%s service=%s kind=%s",
        company_id,
        notification.service,
        notification.type.value,
    )
