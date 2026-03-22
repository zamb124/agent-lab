"""
Push Notification Service.
Вспомогательные функции для работы с push notifications.
Tasks находятся в core.tasks.push_notification_tasks.
"""

from typing import Any, Dict

from apps.flows.src.container import get_container
from a2a.types import (
    PushNotificationAuthenticationInfo,
    PushNotificationConfig,
    TaskPushNotificationConfig,
)

REDIS_PREFIX = "push_notification:"
REDIS_TTL = 86400 * 7  # 7 days


def _get_redis():
    """Получает Redis клиент из контейнера."""
    return get_container().redis_client


def dict_to_config(data: Dict[str, Any]) -> TaskPushNotificationConfig:
    """Конвертирует dict в TaskPushNotificationConfig."""
    push_data = data.get("pushNotificationConfig", {})

    auth = None
    if push_data.get("authentication"):
        auth = PushNotificationAuthenticationInfo(
            credentials=push_data["authentication"].get("credentials"),
            schemes=push_data["authentication"].get("schemes", []),
        )

    return TaskPushNotificationConfig(
        taskId=data["taskId"],
        pushNotificationConfig=PushNotificationConfig(
            id=push_data.get("id"),
            url=push_data["url"],
            token=push_data.get("token"),
            authentication=auth,
        ),
    )
