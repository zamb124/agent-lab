"""
Ядро логики Push Notifications.
Ранее находилось в idle_worker (с зависимостью от flows). Теперь изолировано в core.
"""

import json
import uuid

from core.logging import get_logger
from typing import Any, Dict, List, Optional

from core.clients import RedisClient
from core.http import get_httpx_client
from a2a.types import (
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    TaskPushNotificationConfig,
)
from core.config import get_settings

REDIS_PREFIX = "push_notification:"
REDIS_TTL = 86400 * 7  # 7 days

logger = get_logger(__name__)
# Singleton redis_client для core-задач
_redis_client: Optional[RedisClient] = None

def _get_redis() -> RedisClient:
    """Получает или создает изолированный RedisClient для push уведомлений."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = RedisClient(settings.database.redis_url)
    return _redis_client

async def set_push_config(params: TaskPushNotificationConfig) -> Dict[str, Any]:
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

async def get_push_config(params: GetTaskPushNotificationConfigParams) -> Optional[Dict[str, Any]]:
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

async def list_push_configs(params: ListTaskPushNotificationConfigParams) -> List[Dict[str, Any]]:
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

async def delete_push_config(params: DeleteTaskPushNotificationConfigParams) -> None:
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

async def send_webhook(
    url: str,
    payload: Dict[str, Any],
    token: Optional[str] = None,
    credentials: Optional[str] = None,
) -> Dict[str, Any]:
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
    task_id: str, context_id: str, state: str, message: Optional[str], is_final: bool, webhook_trigger_func
) -> None:
    """Отправляет уведомление всем подписчикам задачи.
    `webhook_trigger_func` - это kiq-вызов, чтобы мы могли ретраить webhooks средствами брокера через worker."""
    params = ListTaskPushNotificationConfigParams(id=task_id)
    configs = await list_push_configs(params)

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

        await webhook_trigger_func(url, payload, token, credentials)
