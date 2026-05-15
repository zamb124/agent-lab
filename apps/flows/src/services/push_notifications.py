"""
Push Notification Service.
Вспомогательные функции для работы с push notifications.
Tasks находятся в apps.idle_worker.tasks.push_notification_tasks.
"""

from typing import Any, Dict

from a2a.types import (
    PushNotificationAuthenticationInfo,
    PushNotificationConfig,
    TaskPushNotificationConfig,
)


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
        task_id=data["taskId"],
        push_notification_config=PushNotificationConfig(
            id=push_data.get("id"),
            url=push_data["url"],
            token=push_data.get("token"),
            authentication=auth,
        ),
    )
