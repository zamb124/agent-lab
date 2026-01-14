"""
WebSocket менеджер для уведомлений платформы.
"""

from core.websocket.manager import (
    notification_manager,
    NotificationManager,
    REDIS_CHANNEL,
)

__all__ = [
    "notification_manager",
    "NotificationManager",
    "REDIS_CHANNEL",
]
