"""
TaskIQ задачи для сервиса frontend.

- send_notification_task: отправка уведомления через WebSocket
"""

from apps.frontend.tasks.notification_tasks import send_notification_task

__all__ = ["send_notification_task"]

