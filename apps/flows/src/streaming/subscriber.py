"""
EventSubscriber - подписка на A2A события из Redis Pub/Sub.
"""

import asyncio
import json
from collections.abc import AsyncIterator

from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.state import TERMINAL_TASK_STATES

from .base import BaseSubscriber, StreamEvent

logger = get_logger(__name__)


def parse_event(data: str) -> StreamEvent:
    """Парсит событие из JSON."""
    parsed = json.loads(data)
    kind = parsed.get("kind")

    if kind == "status-update":
        return TaskStatusUpdateEvent.model_validate(parsed)
    elif kind == "artifact-update":
        return TaskArtifactUpdateEvent.model_validate(parsed)

    raise ValueError(f"Unknown event kind: {kind}")


def is_final_event(event: StreamEvent) -> bool:
    """
    Проверяет является ли событие финальным.

    Финальное событие - TaskStatusUpdateEvent с:
    1. final=True
    2. state в терминальном task state (completed, failed, canceled, input-required)

    Промежуточные события с final=True (например tool_call) НЕ являются финальными!
    """
    if isinstance(event, TaskStatusUpdateEvent):
        if not event.final:
            return False
        state = event.status.state if event.status else None
        if state is None:
            return False
        state_str = state.value if hasattr(state, "value") else str(state)
        if state_str in TERMINAL_TASK_STATES:
            md = event.metadata or {}
            if state_str == "input-required" and md.get("platform_handoff_continue") is True:
                return False
            return True
        return False
    return False


class EventSubscriber(BaseSubscriber):
    """
    Подписывается на A2A события из Redis Pub/Sub.

    Используется в API для получения streaming событий от worker.
    """

    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client

    async def subscribe(
        self,
        task_id: str,
        timeout: float = 300.0,
        ready_event: asyncio.Event | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Подписывается на события задачи.

        Args:
            task_id: ID задачи
            timeout: Таймаут ожидания в секундах
            ready_event: Event для сигнализации о готовности подписки

        Yields:
            A2A события (TaskStatusUpdateEvent или TaskArtifactUpdateEvent)
        """
        channel = f"stream:{task_id}"
        logger.debug(f"[Subscriber] Subscribing to {channel}")

        event_count = 0
        async for message in self.redis.subscribe(channel, timeout=timeout, ready_event=ready_event):
            try:
                event = parse_event(message)
                event_count += 1
                event_kind = message[:50] if isinstance(message, str) else str(type(message))
                logger.debug(f"[Subscriber] Received event #{event_count} on {channel}: {event_kind}")
                yield event

                if is_final_event(event):
                    logger.debug(f"[Subscriber] Final event on {channel}, closing subscription")
                    break

            except Exception as e:
                logger.error(f"[Subscriber] Error parsing event on {channel}: {e}")
                continue

        logger.debug(f"[Subscriber] Subscription ended on {channel}, received {event_count} events")

    async def collect(
        self,
        task_id: str,
        timeout: float = 300.0,
        ready_event: asyncio.Event | None = None,
    ) -> list[StreamEvent]:
        """
        Собирает все события до финального.

        Args:
            task_id: ID задачи
            timeout: Таймаут ожидания в секундах
            ready_event: Event для сигнализации о готовности подписки

        Returns:
            Список всех событий
        """
        events: list[StreamEvent] = []
        async for event in self.subscribe(task_id, timeout=timeout, ready_event=ready_event):
            events.append(event)
        return events


# Алиас для обратной совместимости
RedisSubscriber = EventSubscriber


__all__ = [
    "EventSubscriber",
    "RedisSubscriber",
    "TERMINAL_TASK_STATES",
    "parse_event",
    "is_final_event",
]
