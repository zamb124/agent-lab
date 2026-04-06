"""
Публикация уведомлений из сервисов.
"""

from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from core.websocket.manager import notification_manager
from core.logging import get_logger
from core.push.delivery import deliver_offline_push

logger = get_logger(__name__)


class NotificationType(str, Enum):
    """Типы уведомлений платформы"""

    ACCESS_REQUEST = "access_request"
    ENTITY_UPDATED = "entity_updated"
    TASK_COMPLETED = "task_completed"
    MENTION = "mention"
    SYSTEM = "system"
    SYNC_NEW_MESSAGE = "sync_new_message"
    CRM_DAILY_SUMMARY_UPDATED = "crm_daily_summary_updated"
    CRM_NOTE_UPDATED = "crm_note_updated"
    CRM_KNOWLEDGE_IMPORT_UPDATED = "crm_knowledge_import_updated"
    CALENDAR_NEW_EVENT = "calendar_new_event"
    CALENDAR_SYNC_MEETING_REMINDER = "calendar_sync_meeting_reminder"
    OFFICE_DOCUMENT_SAVED = "office_document_saved"


class Notification(BaseModel):
    """Универсальная модель уведомления"""

    type: NotificationType = Field(description="Тип уведомления")
    title: str = Field(description="Заголовок")
    message: str = Field(description="Текст сообщения")
    data: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные данные")
    service: str = Field(description="Сервис-источник (crm, rag, agents)")
    priority: str = Field(
        default="normal", description="Приоритет (low, normal, high, urgent)"
    )
    action_url: Optional[str] = Field(
        default=None, description="URL для перехода по клику"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время создания",
    )


async def notify_user(user_id: str, notification: Notification):
    """
    Отправить уведомление пользователю.
    
    1. Через WebSocket (если подключен)
    2. Через Web Push (если есть подписка и user offline)
    
    Args:
        user_id: ID пользователя
        notification: Уведомление для отправки
    """
    # WebSocket - real-time
    await notification_manager.publish(user_id, notification.model_dump(mode="json"))
    logger.info(
        f"Уведомление опубликовано: user={user_id}, type={notification.type}, service={notification.service}"
    )
    
    # Офлайн-push (Web Push и/или APNs), если пользователь не в WebSocket
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
