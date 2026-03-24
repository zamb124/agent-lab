"""
Публикация уведомлений из сервисов.
"""

from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from core.websocket.manager import notification_manager
from core.logging import get_logger
from core.push.service import get_web_push_service
from core.push.repository import PushSubscriptionRepository
from core.config import get_settings
logger = get_logger(__name__)


class NotificationType(str, Enum):
    """Типы уведомлений платформы"""

    ACCESS_REQUEST = "access_request"
    ENTITY_UPDATED = "entity_updated"
    TASK_COMPLETED = "task_completed"
    MENTION = "mention"
    SYSTEM = "system"
    SYNC_NEW_MESSAGE = "sync_new_message"


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
    
    # Web Push - если пользователь не подключен через WebSocket
    if not notification_manager.is_user_connected(user_id):
        await _send_web_push(user_id, notification)


async def _send_web_push(user_id: str, notification: Notification):
    """Отправить Web Push уведомление"""

    
    push_service = get_web_push_service()
    if not push_service or not push_service.is_configured:
        return
    
    # Создаем репозиторий с db_url из settings
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url не задан")
    db_url = settings.database.shared_url
    
    repo = PushSubscriptionRepository(db_url=db_url)
    subscriptions = await repo.get_user_subscriptions(user_id)
    
    if not subscriptions:
        return
    
    expired = await push_service.send_to_user(
        subscriptions=subscriptions,
        title=notification.title,
        message=notification.message,
        url=notification.action_url,
        tag=notification.type.value,
        priority=notification.priority,
        data=notification.data
    )
    
    # Удаляем истекшие подписки
    for endpoint in expired:
        await repo.delete_by_endpoint(endpoint)
    
    if expired:
        logger.info(f"Удалено {len(expired)} истекших push подписок")
