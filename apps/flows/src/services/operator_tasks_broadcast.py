"""
Real-time обновление канбана оператора: публикация в Redis platform:notifications.

Используется Redis-клиент контейнера (API и TaskIQ worker), без notify_user —
без Web Push и без зависимости от notification_manager._redis_client в воркере.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.flows.src.db.operator_repository import OperatorRepository
from core.logging import get_logger
from core.websocket.manager import REDIS_CHANNEL
from core.websocket.publisher import Notification, NotificationType

if TYPE_CHECKING:
    from core.clients.redis_client import RedisClient

logger = get_logger(__name__)


async def publish_operator_tasks_refresh(
    redis_client: RedisClient,
    repo: OperatorRepository,
    queue_id: str,
) -> None:
    user_ids = await repo.list_user_ids_for_queue(queue_id)
    if not user_ids:
        return

    notification = Notification(
        type=NotificationType.FLOWS_OPERATOR_TASKS_UPDATED,
        title="Operator queue",
        message="New task received",
        service="flows",
        data={"queue_id": queue_id},
        priority="low",
    )
    payload_dict = notification.model_dump(mode="json")
    ts = datetime.now(timezone.utc).isoformat()

    for uid in user_ids:
        envelope = json.dumps(
            {
                "user_id": uid,
                "notification": payload_dict,
                "timestamp": ts,
            }
        )
        await redis_client.publish(REDIS_CHANNEL, envelope)

    logger.debug(
        "Operator tasks refresh published: queue_id=%s recipients=%s",
        queue_id,
        len(user_ids),
    )
