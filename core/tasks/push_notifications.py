"""
Ядро логики Push Notifications.
Ранее находилось в idle_worker (с зависимостью от flows). Теперь изолировано в core.
"""

import json
import uuid
from collections.abc import Awaitable, Callable

from a2a.types import (
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    PushNotificationConfig,
    TaskPushNotificationConfig,
)

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.http import get_httpx_client
from core.logging import get_logger
from core.types import JsonArray, JsonObject, parse_json_array, parse_json_object

REDIS_PREFIX = "push_notification:"
REDIS_TTL = 86400 * 7  # 7 суток

logger = get_logger(__name__)
# Singleton-экземпляр redis_client для core-задач
_redis_client: RedisClient | None = None


def _get_redis() -> RedisClient:
    """Получает или создает изолированный RedisClient для push уведомлений."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = RedisClient(settings.database.redis_url)
    return _redis_client


def _config_to_json(config: TaskPushNotificationConfig) -> str:
    return config.model_dump_json(by_alias=True)


def _config_from_json(data: str) -> TaskPushNotificationConfig:
    return TaskPushNotificationConfig.model_validate(
        parse_json_object(data, "TaskPushNotificationConfig")
    )


def _config_id_list_from_json(data: str) -> list[str]:
    config_ids: JsonArray = parse_json_array(data, "push notification config ids")
    result: list[str] = []
    for config_id in config_ids:
        if not isinstance(config_id, str):
            raise ValueError("push notification config ids must be strings")
        result.append(config_id)
    return result


def _config_id_list_to_json(config_ids: list[str]) -> str:
    return json.dumps(config_ids)


async def _load_config_ids(redis: RedisClient, task_id: str) -> list[str]:
    existing = await redis.get(f"{REDIS_PREFIX}{task_id}:configs")
    if existing is None:
        return []
    return _config_id_list_from_json(existing)


async def set_push_config(params: TaskPushNotificationConfig) -> TaskPushNotificationConfig:
    """Сохраняет конфигурацию push notification."""
    redis = _get_redis()

    task_id = params.task_id
    push_config = params.push_notification_config
    config_id = push_config.id if push_config.id is not None else str(uuid.uuid4())
    stored_config = TaskPushNotificationConfig(
        task_id=task_id,
        push_notification_config=PushNotificationConfig(
            authentication=push_config.authentication,
            id=config_id,
            token=push_config.token,
            url=push_config.url,
        ),
    )

    key = f"{REDIS_PREFIX}{task_id}:{config_id}"
    _ = await redis.set(key, _config_to_json(stored_config), ttl=REDIS_TTL)

    configs_key = f"{REDIS_PREFIX}{task_id}:configs"
    config_ids = await _load_config_ids(redis, task_id)
    if config_id not in config_ids:
        config_ids.append(config_id)
        _ = await redis.set(configs_key, _config_id_list_to_json(config_ids), ttl=REDIS_TTL)

    logger.info(f"Push config saved: task={task_id}, config={config_id}")
    return stored_config


async def get_push_config(
    params: GetTaskPushNotificationConfigParams,
) -> TaskPushNotificationConfig | None:
    """Получает конфигурацию push notification."""
    redis = _get_redis()
    task_id = params.id
    config_id = params.push_notification_config_id

    if config_id:
        key = f"{REDIS_PREFIX}{task_id}:{config_id}"
        data = await redis.get(key)
        return _config_from_json(data) if data is not None else None

    config_ids = await _load_config_ids(redis, task_id)
    if not config_ids:
        return None

    key = f"{REDIS_PREFIX}{task_id}:{config_ids[0]}"
    data = await redis.get(key)
    return _config_from_json(data) if data is not None else None


async def list_push_configs(params: ListTaskPushNotificationConfigParams) -> list[TaskPushNotificationConfig]:
    """Список конфигураций для задачи."""
    redis = _get_redis()
    task_id = params.id

    config_ids = await _load_config_ids(redis, task_id)
    if not config_ids:
        return []

    result: list[TaskPushNotificationConfig] = []

    for cid in config_ids:
        key = f"{REDIS_PREFIX}{task_id}:{cid}"
        data = await redis.get(key)
        if data is not None:
            result.append(_config_from_json(data))

    return result


async def delete_push_config(params: DeleteTaskPushNotificationConfigParams) -> None:
    """Удаляет конфигурацию push notification."""
    redis = _get_redis()
    task_id = params.id
    config_id = params.push_notification_config_id

    key = f"{REDIS_PREFIX}{task_id}:{config_id}"
    _ = await redis.delete(key)

    configs_key = f"{REDIS_PREFIX}{task_id}:configs"
    existing = await redis.get(configs_key)
    if existing is not None:
        config_ids = _config_id_list_from_json(existing)
        if config_id in config_ids:
            config_ids.remove(config_id)
            _ = await redis.set(configs_key, _config_id_list_to_json(config_ids), ttl=REDIS_TTL)

    logger.info(f"Push config deleted: task={task_id}, config={config_id}")


async def send_webhook(
    url: str,
    payload: JsonObject,
    token: str | None = None,
    credentials: str | None = None,
) -> JsonObject:
    """Отправляет webhook."""
    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif credentials:
        headers["Authorization"] = credentials

    async with get_httpx_client(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code >= 400:
            raise RuntimeError(f"Webhook {url} returned {response.status_code}")

        logger.info(f"Push notification sent to {url}")
        return {"success": True, "status_code": response.status_code}


async def process_send_task_update(
    task_id: str,
    context_id: str,
    state: str,
    message: str | None,
    is_final: bool,
    webhook_trigger_func: Callable[
        [str, JsonObject, str | None, str | None],
        Awaitable[None],
    ],
) -> None:
    """Отправляет уведомление всем подписчикам задачи.
    `webhook_trigger_func` - это kiq-вызов, чтобы мы могли ретраить webhooks средствами брокера через worker."""
    params = ListTaskPushNotificationConfigParams(id=task_id)
    configs = await list_push_configs(params)

    if not configs:
        return

    status: JsonObject = {
        "state": state,
        "message": None,
    }
    if message is not None:
        status["message"] = {
            "role": "agent",
            "parts": [{"kind": "text", "text": message}],
        }

    payload: JsonObject = {
        "jsonrpc": "2.0",
        "method": "tasks/pushNotification",
        "params": {
            "taskId": task_id,
            "contextId": context_id,
            "status": status,
            "final": is_final,
        },
    }

    for config in configs:
        push_config = config.push_notification_config
        auth = push_config.authentication
        credentials = auth.credentials if auth is not None else None

        await webhook_trigger_func(push_config.url, payload, push_config.token, credentials)
