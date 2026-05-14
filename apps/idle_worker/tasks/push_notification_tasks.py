"""
TaskIQ tasks для push notifications.
Проксирует вызовы в core.tasks.push_notifications (где изолирована логика).
"""

from typing import Any, Dict, List, Optional

from a2a.types import (
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    TaskPushNotificationConfig,
)

from apps.idle_worker.broker import broker as idle_broker
from core.tasks.push_notifications import (
    delete_push_config,
    get_push_config,
    list_push_configs,
    process_send_task_update,
    set_push_config,
)
from core.tasks.push_notifications import (
    send_webhook as core_send_webhook,
)


@idle_broker.task(task_name="push_config_set", queue_name="idle")
async def set_config(params: TaskPushNotificationConfig) -> Dict[str, Any]:
    """Сохраняет конфигурацию push notification."""
    return await set_push_config(params)


@idle_broker.task(task_name="push_config_get", queue_name="idle")
async def get_config(params: GetTaskPushNotificationConfigParams) -> Optional[Dict[str, Any]]:
    """Получает конфигурацию push notification."""
    return await get_push_config(params)


@idle_broker.task(task_name="push_config_list", queue_name="idle")
async def list_configs(params: ListTaskPushNotificationConfigParams) -> List[Dict[str, Any]]:
    """Список конфигураций для задачи."""
    return await list_push_configs(params)


@idle_broker.task(task_name="push_config_delete", queue_name="idle")
async def delete_config(params: DeleteTaskPushNotificationConfigParams) -> None:
    """Удаляет конфигурацию push notification."""
    await delete_push_config(params)


@idle_broker.task(
    task_name="push_notification_send",
    retry_on_error=True,
    max_retries=5,
    default_retry_delay=5.0,
    queue_name="idle"
)
async def send_webhook(
    url: str,
    payload: Dict[str, Any],
    token: Optional[str] = None,
    credentials: Optional[str] = None,
) -> Dict[str, Any]:
    """Отправляет webhook с ретраями чере TaskIQ."""
    return await core_send_webhook(url, payload, token, credentials)


@idle_broker.task(
    task_name="send_task_update",
    retry_on_error=True,
    max_retries=3,
    queue_name="idle"
)
async def send_task_update(
    task_id: str, context_id: str, state: str, message: Optional[str] = None, is_final: bool = False
) -> None:
    """Отправляет уведомление всем подписчикам задачи."""
    await process_send_task_update(
        task_id, context_id, state, message, is_final, webhook_trigger_func=send_webhook.kiq
    )


@idle_broker.task(task_name="send_task_completed", queue_name="idle")
async def send_task_completed(task_id: str, context_id: str, response: str) -> None:
    """Уведомление о завершении."""
    await send_task_update(task_id, context_id, "completed", response, True)


@idle_broker.task(task_name="send_task_failed", queue_name="idle")
async def send_task_failed(task_id: str, context_id: str, error: str) -> None:
    """Уведомление об ошибке."""
    await send_task_update(task_id, context_id, "failed", f"Error: {error}", True)


@idle_broker.task(task_name="send_task_input_required", queue_name="idle")
async def send_task_input_required(task_id: str, context_id: str, question: str) -> None:
    """Уведомление о необходимости ввода."""
    await send_task_update(task_id, context_id, "input-required", question, True)

