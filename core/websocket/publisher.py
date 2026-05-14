"""
Публикация уведомлений пользователям.

Чисто event-driven: каждый сервис формирует доменное событие через
`publish_ui_event_to_user(user_id, type, payload, ...)` (см.
`core/ui_events/dispatcher.py`). Этот модуль предоставляет тонкий
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
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.logging import get_logger
from core.push.delivery import deliver_offline_push
from core.ui_events.contract import UIEvent, UIEventMeta, UIEventTarget, assert_ui_event_type
from core.ui_events.dispatcher import publish_ui_event
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
    OFFICE_DOCUMENT_SAVED = "office_document_saved"
    FLOWS_OPERATOR_TASKS_UPDATED = "flows_operator_tasks_updated"


class NotificationAction(BaseModel):
    """Структурированная ссылка/действие внутри уведомления."""

    label: str = ""
    url: str
    label_i18n_key: Optional[str] = None
    label_i18n_vars: Dict[str, Any] = Field(default_factory=dict)
    data: Dict[str, Any] = Field(default_factory=dict)


class Notification(BaseModel):
    """Уведомление для пользователя — превращается в UIEvent + опционально push."""

    type: NotificationType
    title: str
    message: str
    title_i18n_key: Optional[str] = None
    title_i18n_vars: Dict[str, Any] = Field(default_factory=dict)
    message_i18n_key: Optional[str] = None
    message_i18n_vars: Dict[str, Any] = Field(default_factory=dict)
    data: Dict[str, Any] = Field(default_factory=dict)
    service: str
    priority: str = "normal"
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    action_label_i18n_key: Optional[str] = None
    actions: List[NotificationAction] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _event_type_for(notification: Notification) -> str:
    candidate = f"notify/{notification.service}/{notification.type.value}_received"
    return assert_ui_event_type(candidate)


async def notify_user(user_id: str, notification: Notification) -> None:
    """
    Доставить уведомление пользователю.

    1. Публикуется как UIEvent в платформенный канал `platform:ui_events`
       — фронт получает его через WebSocket и обрабатывает в EventBus.
    2. Если пользователь offline — отправляется Web Push / APNs через
       `deliver_offline_push`.
    """
    event_type = _event_type_for(notification)
    payload = {
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
        "actions": [action.model_dump() for action in notification.actions],
        "created_at": notification.created_at.isoformat(),
        "service": notification.service,
        "kind": notification.type.value,
    }
    event = UIEvent(type=event_type, payload=payload, meta=UIEventMeta(source="system"))
    await publish_ui_event(event, UIEventTarget(user_id=user_id))
    logger.info(
        "Notification published: user=%s service=%s kind=%s",
        user_id,
        notification.service,
        notification.type.value,
    )

    if not notification_manager.is_user_connected(user_id):
        await deliver_offline_push(
            user_id,
            title=notification.title,
            message=notification.message,
            action_url=notification.action_url,
            tag=notification.type.value,
            priority=notification.priority,
            data=notification.data,
        )
