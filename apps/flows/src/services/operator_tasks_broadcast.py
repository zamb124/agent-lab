"""
Real-time обновление канбана оператора: публикация UI-события через
единый `core.ui_events.publish_ui_event_to_user`.

Вызывается как из HTTP-процесса flows, так и из TaskIQ worker. В обоих
случаях используется один и тот же dispatcher — `notification_manager`
лениво поднимает Redis publisher при первом вызове (см.
`core/websocket/manager.py::NotificationManager._ensure_publisher_client`).
"""

from __future__ import annotations

from apps.flows.src.db.operator_repository import OperatorRepository
from core.logging import get_logger
from core.ui_events.dispatcher import publish_ui_event_to_user

logger = get_logger(__name__)

OPERATOR_TASKS_REFRESH_EVENT_TYPE = "notify/flows/flows_operator_tasks_updated_received"


async def publish_operator_tasks_refresh(
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
        await publish_ui_event_to_user(
            user_id=uid,
            type=OPERATOR_TASKS_REFRESH_EVENT_TYPE,
            payload=payload,
        )

    logger.debug(
        "Operator tasks refresh published: queue_id=%s recipients=%s",
        queue_id,
        len(user_ids),
    )
