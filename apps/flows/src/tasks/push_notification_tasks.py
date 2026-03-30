"""
TaskIQ tasks для push notifications.
"""

import json
import uuid
from typing import Any, Dict, List, Optional

import httpx
from core.http import get_httpx_client
from a2a.types import (
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    TaskPushNotificationConfig,
)

from core.logging import get_logger
from apps.flows.src.services.push_notifications import REDIS_PREFIX, REDIS_TTL, _get_redis

from apps.idle_worker.broker import broker as idle_broker

logger = get_logger(__name__)


@idle_broker.task(task_name="push_config_set", queue_name="idle")
async def set_config(params: TaskPushNotificationConfig) -> Dict[str, Any]:
    """Сохраняет конфигурацию push notification."""
    redis = _get_redis()

    task_id = params.task_id
    push_config = params.push_notification_config
    config_id = push_config.id or str(uuid.uuid4())

    auth_data = None
    if push_config.authentication:
        auth_data = {
            "credentials": push_config.authentication.credentials,
            "schemes": push_config.authentication.schemes or [],
        }

    data = {
        "taskId": task_id,
        "pushNotificationConfig": {
            "id": config_id,
            "url": push_config.url,
            "token": push_config.token,
            "authentication": auth_data,
        },
    }

    key = f"{REDIS_PREFIX}{task_id}:{config_id}"
    await redis.set(key, json.dumps(data), ttl=REDIS_TTL)

    configs_key = f"{REDIS_PREFIX}{task_id}:configs"
    existing = await redis.get(configs_key)
    config_ids = json.loads(existing) if existing else []
    if config_id not in config_ids:
        config_ids.append(config_id)
        await redis.set(configs_key, json.dumps(config_ids), ttl=REDIS_TTL)

    logger.info(f"Push config saved: task={task_id}, config={config_id}")
    return data


@idle_broker.task(task_name="push_config_get", queue_name="idle")
async def get_config(params: GetTaskPushNotificationConfigParams) -> Optional[Dict[str, Any]]:
    """Получает конфигурацию push notification."""
    redis = _get_redis()
    task_id = params.id
    config_id = params.push_notification_config_id

    if config_id:
        key = f"{REDIS_PREFIX}{task_id}:{config_id}"
        data = await redis.get(key)
        return json.loads(data) if data else None

    configs_key = f"{REDIS_PREFIX}{task_id}:configs"
    existing = await redis.get(configs_key)
    if not existing:
        return None

    config_ids = json.loads(existing)
    if not config_ids:
        return None

    key = f"{REDIS_PREFIX}{task_id}:{config_ids[0]}"
    data = await redis.get(key)
    return json.loads(data) if data else None


@idle_broker.task(task_name="push_config_list", queue_name="idle")
async def list_configs(params: ListTaskPushNotificationConfigParams) -> List[Dict[str, Any]]:
    """Список конфигураций для задачи."""
    redis = _get_redis()
    task_id = params.id

    configs_key = f"{REDIS_PREFIX}{task_id}:configs"
    existing = await redis.get(configs_key)

    if not existing:
        return []

    config_ids = json.loads(existing)
    result = []

    for cid in config_ids:
        key = f"{REDIS_PREFIX}{task_id}:{cid}"
        data = await redis.get(key)
        if data:
            result.append(json.loads(data))

    return result


@idle_broker.task(task_name="push_config_delete", queue_name="idle")
async def delete_config(params: DeleteTaskPushNotificationConfigParams) -> None:
    """Удаляет конфигурацию push notification."""
    redis = _get_redis()
    task_id = params.id
    config_id = params.push_notification_config_id

    key = f"{REDIS_PREFIX}{task_id}:{config_id}"
    await redis.delete(key)

    configs_key = f"{REDIS_PREFIX}{task_id}:configs"
    existing = await redis.get(configs_key)
    if existing:
        config_ids = json.loads(existing)
        if config_id in config_ids:
            config_ids.remove(config_id)
            await redis.set(configs_key, json.dumps(config_ids), ttl=REDIS_TTL)

    logger.info(f"Push config deleted: task={task_id}, config={config_id}")


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
    """Отправляет webhook с ретраями."""
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
    params = ListTaskPushNotificationConfigParams(id=task_id)
    configs = await list_configs(params)

    if not configs:
        return

    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/pushNotification",
        "params": {
            "taskId": task_id,
            "contextId": context_id,
            "status": {
                "state": state,
                "message": {"role": "agent", "parts": [{"kind": "text", "text": message or ""}]}
                if message
                else None,
            },
            "final": is_final,
        },
    }

    for config_data in configs:
        push_config = config_data.get("pushNotificationConfig", {})
        url = push_config.get("url")
        if not url:
            continue

        token = push_config.get("token")
        auth = push_config.get("authentication", {})
        credentials = auth.get("credentials") if auth else None

        await send_webhook.kiq(url, payload, token, credentials)


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

