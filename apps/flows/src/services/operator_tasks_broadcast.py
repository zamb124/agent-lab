"""
Real-time обновление канбана оператора: публикация UIEvent в Redis-канал
`platform:ui_events` через RedisClient контейнера.

Прямая публикация (а не `notify_user`) нужна потому, что вызовы случаются
в том числе из TaskIQ worker, где singleton `notification_manager._redis_client`
не инициализирован, а push-доставку в этом потоке делать не нужно — UI
сам перезагружает канбан по событию.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from apps.flows.src.db.operator_repository import OperatorRepository
from core.logging import get_logger
from core.ui_events.contract import UIEvent, UIEventMeta, UIEventTarget
from core.ui_events.dispatcher import UI_EVENTS_REDIS_CHANNEL

if TYPE_CHECKING:
    from core.clients.redis_client import RedisClient

logger = get_logger(__name__)

OPERATOR_TASKS_REFRESH_EVENT_TYPE = "notify/flows/flows_operator_tasks_updated_received"


async def publish_operator_tasks_refresh(
    redis_client: RedisClient,
    repo: OperatorRepository,
    queue_id: str,
) -> None:
    user_ids = await repo.list_user_ids_for_queue(queue_id)
    if not user_ids:
        return

    payload = {
        "service": "flows",
        "kind": "flows_operator_tasks_updated",
        "data": {"queue_id": queue_id},
        "priority": "low",
    }

    for uid in user_ids:
        event = UIEvent(
            type=OPERATOR_TASKS_REFRESH_EVENT_TYPE,
            payload=payload,
            meta=UIEventMeta(source="system"),
        )
        target = UIEventTarget(user_id=uid)
        target.assert_valid()
        envelope = json.dumps(
            {
                "target": target.model_dump(mode="json"),
                "event": event.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
        await redis_client.publish(UI_EVENTS_REDIS_CHANNEL, envelope)

    logger.debug(
        "Operator tasks refresh published: queue_id=%s recipients=%s",
        queue_id,
        len(user_ids),
    )
