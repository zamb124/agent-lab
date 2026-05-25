"""
TaskIQ tasks для push notifications.
Проксирует вызовы в core.tasks.push_notifications (где изолирована логика).
"""

from a2a.types import (
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    TaskPushNotificationConfig,
)

from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.tasks.task_names import (
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
from core.types import JsonObject, parse_json_object


@idle_broker.task(task_name=TASK_PUSH_CONFIG_SET, queue_name="idle")
async def set_config(params: TaskPushNotificationConfig) -> JsonObject:
    """Сохраняет конфигурацию push notification."""
    config = await set_push_config(params)
    return parse_json_object(config.model_dump_json(by_alias=True), "TaskPushNotificationConfig")


@idle_broker.task(task_name=TASK_PUSH_CONFIG_GET, queue_name="idle")
async def get_config(params: GetTaskPushNotificationConfigParams) -> JsonObject | None:
    """Получает конфигурацию push notification."""
    config = await get_push_config(params)
    if config is None:
        return None
    return parse_json_object(config.model_dump_json(by_alias=True), "TaskPushNotificationConfig")


@idle_broker.task(task_name=TASK_PUSH_CONFIG_LIST, queue_name="idle")
async def list_configs(params: ListTaskPushNotificationConfigParams) -> list[JsonObject]:
    """Список конфигураций для задачи."""
    configs = await list_push_configs(params)
    return [
        parse_json_object(config.model_dump_json(by_alias=True), "TaskPushNotificationConfig")
        for config in configs
    ]


@idle_broker.task(task_name=TASK_PUSH_CONFIG_DELETE, queue_name="idle")
async def delete_config(params: DeleteTaskPushNotificationConfigParams) -> None:
    """Удаляет конфигурацию push notification."""
    await delete_push_config(params)


@idle_broker.task(
    task_name=TASK_PUSH_NOTIFICATION_SEND,
    retry_on_error=True,
    max_retries=5,
    default_retry_delay=5.0,
    queue_name="idle"
)
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
    _ = await send_webhook.kiq(url, payload, token, credentials)


@idle_broker.task(
    task_name=TASK_SEND_TASK_UPDATE,
    retry_on_error=True,
    max_retries=3,
    queue_name="idle"
)
async def send_task_update(
    task_id: str, context_id: str, state: str, message: str | None = None, is_final: bool = False
) -> None:
    """Отправляет уведомление всем подписчикам задачи."""
    await process_send_task_update(
        task_id, context_id, state, message, is_final, webhook_trigger_func=_enqueue_webhook
    )


@idle_broker.task(task_name=TASK_SEND_TASK_COMPLETED, queue_name="idle")
async def send_task_completed(task_id: str, context_id: str, response: str) -> None:
    """Уведомление о завершении."""
    await send_task_update(task_id, context_id, "completed", response, True)


@idle_broker.task(task_name=TASK_SEND_TASK_FAILED, queue_name="idle")
async def send_task_failed(task_id: str, context_id: str, error: str) -> None:
    """Уведомление об ошибке."""
    await send_task_update(task_id, context_id, "failed", f"Error: {error}", True)


@idle_broker.task(task_name=TASK_SEND_TASK_INPUT_REQUIRED, queue_name="idle")
async def send_task_input_required(task_id: str, context_id: str, question: str) -> None:
    """Уведомление о необходимости ввода."""
    await send_task_update(task_id, context_id, "input-required", question, True)
