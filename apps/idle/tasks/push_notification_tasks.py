"""
TaskIQ tasks для push notifications.
Проксирует вызовы в core.tasks.push_notifications (где изолирована логика).
"""

from a2a.types import (
    DeleteTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigRequest,
    ListTaskPushNotificationConfigsRequest,
    TaskPushNotificationConfig,
)
from google.protobuf.json_format import MessageToDict

from apps.idle.tasks.task_names import (
    TASK_PUSH_CONFIG_DELETE,
    TASK_PUSH_CONFIG_GET,
    TASK_PUSH_CONFIG_LIST,
    TASK_PUSH_CONFIG_SET,
    TASK_PUSH_NOTIFICATION_SEND,
    TASK_SEND_TASK_COMPLETED,
    TASK_SEND_TASK_FAILED,
    TASK_SEND_TASK_INPUT_REQUIRED,
    TASK_SEND_TASK_UPDATE,
)
from core.tasks import enqueue, platform_task
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
from core.types import JsonObject, require_json_object


@platform_task(TASK_PUSH_CONFIG_SET)
async def set_config(params: TaskPushNotificationConfig) -> JsonObject:
    """Сохраняет конфигурацию push notification."""
    config = await set_push_config(params)
    return require_json_object(MessageToDict(config), "TaskPushNotificationConfig")


@platform_task(TASK_PUSH_CONFIG_GET)
async def get_config(params: GetTaskPushNotificationConfigRequest) -> JsonObject | None:
    """Получает конфигурацию push notification."""
    config = await get_push_config(params)
    if config is None:
        return None
    return require_json_object(MessageToDict(config), "TaskPushNotificationConfig")


@platform_task(TASK_PUSH_CONFIG_LIST)
async def list_configs(params: ListTaskPushNotificationConfigsRequest) -> JsonObject:
    """Список конфигураций для задачи."""
    response = await list_push_configs(params)
    return require_json_object(MessageToDict(response), "ListTaskPushNotificationConfigsResponse")


@platform_task(TASK_PUSH_CONFIG_DELETE)
async def delete_config(params: DeleteTaskPushNotificationConfigRequest) -> None:
    """Удаляет конфигурацию push notification."""
    await delete_push_config(params)


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


@platform_task(TASK_SEND_TASK_COMPLETED)
async def send_task_completed(task_id: str, context_id: str, response: str) -> None:
    """Уведомление о завершении."""
    await send_task_update(task_id, context_id, "completed", response, True)


@platform_task(TASK_SEND_TASK_FAILED)
async def send_task_failed(task_id: str, context_id: str, error: str) -> None:
    """Уведомление об ошибке."""
    await send_task_update(task_id, context_id, "failed", f"Error: {error}", True)


@platform_task(TASK_SEND_TASK_INPUT_REQUIRED)
async def send_task_input_required(task_id: str, context_id: str, question: str) -> None:
    """Уведомление о необходимости ввода."""
    await send_task_update(task_id, context_id, "input-required", question, True)
