"""
TaskIQ tasks для push notifications.
Проксирует вызовы в core.tasks.push_notifications (где изолирована логика).
"""

from apps.idle.tasks.task_names import (
    TASK_PUSH_NOTIFICATION_SEND,
    TASK_SEND_TASK_UPDATE,
)
from core.tasks import enqueue, platform_task
from core.tasks.push_notifications import (
    process_send_task_update,
)
from core.tasks.push_notifications import (
    send_webhook as core_send_webhook,
)
from core.types import JsonObject


@platform_task(TASK_PUSH_NOTIFICATION_SEND)
async def send_webhook(
    url: str,
    payload: JsonObject,
    token: str | None = None,
    credentials: str | None = None,
) -> JsonObject:
    """Отправляет webhook с ретраями чере TaskIQ."""
    return await core_send_webhook(url, payload, token, credentials)


async def _enqueue_webhook(
    url: str,
    payload: JsonObject,
    token: str | None,
    credentials: str | None,
) -> None:
    _ = await enqueue(TASK_PUSH_NOTIFICATION_SEND, url, payload, token, credentials)


@platform_task(TASK_SEND_TASK_UPDATE)
async def send_task_update(
    task_id: str, context_id: str, state: str, message: str | None = None, is_final: bool = False
) -> None:
    """Отправляет уведомление всем подписчикам задачи."""
    await process_send_task_update(
        task_id, context_id, state, message, is_final, webhook_trigger_func=_enqueue_webhook
    )
