"""
EventSubscriber - подписка на A2A события из Redis Pub/Sub.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import override

from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from pydantic import ValidationError

from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.state import TERMINAL_TASK_STATES
from core.types import JsonObject, parse_json_object, require_json_object

from .base import BaseSubscriber, StreamEvent

logger = get_logger(__name__)


def _is_agent_handoff_input_required(metadata: JsonObject) -> bool:
    interrupt_value = metadata.get("platform_interrupt")
    if interrupt_value is None:
        return False
    platform_interrupt = require_json_object(interrupt_value, "metadata.platform_interrupt")
    body_value = platform_interrupt.get("body")
    if body_value is None:
        return False
    body = require_json_object(body_value, "metadata.platform_interrupt.body")
    return body.get("kind") == "handoff"


def parse_event(data: str) -> StreamEvent:
    """Парсит событие из JSON."""
    parsed = parse_json_object(data, "StreamEvent")
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
        state = event.status.state if event.status else None
        if state is None:
            return False
        state_str = state.value
        metadata_raw = event.metadata
        metadata: JsonObject = (
            require_json_object(metadata_raw, "TaskStatusUpdateEvent.metadata")
            if metadata_raw is not None
            else {}
        )
        if state_str == "input-required":
            if _is_agent_handoff_input_required(metadata):
                return True
            if metadata.get("platform_handoff_continue") is True:
                return False
        if not event.final:
            return False
        if state_str in TERMINAL_TASK_STATES:
            return True
        return False
    return False


class EventSubscriber(BaseSubscriber):
    """
    Подписывается на A2A события из Redis Pub/Sub.

    Используется в API для получения streaming событий от worker.
    """

    redis: RedisClient

    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client

    @override
    async def subscribe(
        self,
        task_id: str,
        timeout: float = 300.0,
        ready_event: asyncio.Event | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Подписывается на события задачи.

        Аргументы:
            task_id: ID задачи
            timeout: Таймаут ожидания в секундах
            ready_event: Event для сигнализации о готовности подписки

        Генерирует:
            A2A-события (TaskStatusUpdateEvent или TaskArtifactUpdateEvent)
        """
        channel = f"stream:{task_id}"
        logger.debug(f"[Subscriber] Subscribing to {channel}")

        event_count = 0
        async for message in self.redis.subscribe(channel, timeout=timeout, ready_event=ready_event):
            try:
                event = parse_event(message)
            except (ValueError, ValidationError) as e:
                logger.error(f"[Subscriber] Error parsing event on {channel}: {e}")
                continue
            event_count += 1
            event_kind = message[:50]
            logger.debug(f"[Subscriber] Received event #{event_count} on {channel}: {event_kind}")
            yield event

            if is_final_event(event):
                logger.debug(f"[Subscriber] Final event on {channel}, closing subscription")
                break

        logger.debug(f"[Subscriber] Subscription ended on {channel}, received {event_count} events")

    @override
    async def collect(
        self,
        task_id: str,
        timeout: float = 300.0,
        ready_event: asyncio.Event | None = None,
    ) -> list[StreamEvent]:
        """
        Собирает все события до финального.

        Аргументы:
            task_id: ID задачи
            timeout: Таймаут ожидания в секундах
            ready_event: Event для сигнализации о готовности подписки

        Возвращает:
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
