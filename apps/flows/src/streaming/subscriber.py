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
from google.protobuf.json_format import ParseDict
from google.protobuf.message import DecodeError

from core.a2a import (
    a2a_task_state_to_platform,
    is_interrupted_a2a_task_state,
    is_terminal_a2a_task_state,
    mapping_from_struct,
)
from core.clients.redis_client import RedisClient
from core.logging import get_logger
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


def _is_operator_task_input_required(metadata: JsonObject) -> bool:
    interrupt_value = metadata.get("platform_interrupt")
    if interrupt_value is None:
        return False
    platform_interrupt = require_json_object(interrupt_value, "metadata.platform_interrupt")
    body_value = platform_interrupt.get("body")
    if body_value is None:
        return False
    body = require_json_object(body_value, "metadata.platform_interrupt.body")
    return body.get("kind") == "operator_task"


def _event_metadata(event: TaskStatusUpdateEvent) -> JsonObject:
    if not event.HasField("metadata"):
        return {}
    return mapping_from_struct(event.metadata)


def parse_event(data: str) -> StreamEvent:
    """Парсит A2A 1.0 событие из JSON (StreamResponse или плоский status/artifact update)."""
    parsed = parse_json_object(data, "StreamEvent")

    # StreamResponse shape: {statusUpdate:...} / {artifactUpdate:...}
    status_update = parsed.get("statusUpdate")
    if isinstance(status_update, dict):
        event = TaskStatusUpdateEvent()
        _ = ParseDict(status_update, event)
        return event
    artifact_update = parsed.get("artifactUpdate")
    if isinstance(artifact_update, dict):
        event = TaskArtifactUpdateEvent()
        _ = ParseDict(artifact_update, event)
        return event

    # Плоский TaskStatusUpdateEvent / TaskArtifactUpdateEvent (MessageToDict)
    if "status" in parsed and "taskId" in parsed:
        event = TaskStatusUpdateEvent()
        _ = ParseDict(dict(parsed), event)
        return event
    if "artifact" in parsed and "taskId" in parsed:
        event = TaskArtifactUpdateEvent()
        _ = ParseDict(dict(parsed), event)
        return event

    # A2A Protocol 0.3 stream kind — hard cut reject (not accepted on 1.0 wire)
    kind = parsed.get("kind")
    if kind in ("status-update", "artifact-update"):
        raise ValueError(f"A2A 0.3 event kind rejected: {kind!r}")

    raise ValueError(f"Unknown A2A stream event shape: keys={sorted(parsed.keys())}")


def is_final_event(event: StreamEvent) -> bool:
    """
    Финальное событие — TaskStatusUpdateEvent с terminal/interrupted state.

    `final=` удалён в A2A 1.0; критерий — protobuf TaskState + platform interrupt metadata.
    """
    if not isinstance(event, TaskStatusUpdateEvent):
        return False
    if not event.HasField("status"):
        return False
    state = event.status.state
    metadata = _event_metadata(event)
    platform_state = a2a_task_state_to_platform(state)

    if platform_state == "input-required":
        if _is_agent_handoff_input_required(metadata):
            return True
        # HITL: закрываем SendStreamingMessage; user/operator идут на live SubscribeToTask.
        if _is_operator_task_input_required(metadata):
            return True
        if metadata.get("platform_handoff_continue") is True:
            return False
        if metadata.get("platform_oauth_continue") is True:
            return False
        return True

    if is_terminal_a2a_task_state(state):
        return True
    if is_interrupted_a2a_task_state(state):
        return True
    return False


def event_platform_sequence(event: StreamEvent) -> int | None:
    """``metadata.platformSequence`` durable-события (None — событие без ledger-курсора)."""
    if not event.HasField("metadata"):
        return None
    metadata = mapping_from_struct(event.metadata)
    sequence = metadata.get("platformSequence")
    if sequence is None:
        return None
    if isinstance(sequence, bool):
        raise ValueError("A2A event metadata.platformSequence must be a positive int")
    if isinstance(sequence, float):
        if not sequence.is_integer():
            raise ValueError("A2A event metadata.platformSequence must be a positive int")
        sequence = int(sequence)
    if not isinstance(sequence, int) or sequence < 1:
        raise ValueError("A2A event metadata.platformSequence must be a positive int")
    return sequence


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
        *,
        after_sequence: int = 0,
    ) -> AsyncIterator[StreamEvent]:
        """
        Подписывается на события задачи.

        Аргументы:
            task_id: ID задачи
            timeout: Таймаут ожидания в секундах
            ready_event: Event для сигнализации о готовности подписки
            after_sequence: пропускать live events с platformSequence <= after_sequence

        Генерирует:
            A2A-события (TaskStatusUpdateEvent или TaskArtifactUpdateEvent)
        """
        if after_sequence < 0:
            raise ValueError("after_sequence must be >= 0")
        channel = f"stream:{task_id}"
        logger.debug("flows.stream.subscribe", channel=channel)

        event_count = 0
        async for message in self.redis.subscribe(channel, timeout=timeout, ready_event=ready_event):
            try:
                event = parse_event(message)
            except (ValueError, DecodeError, TypeError) as e:
                logger.error("flows.stream.parse_failed", channel=channel, error=str(e))
                continue
            sequence = event_platform_sequence(event)
            if sequence is not None and sequence <= after_sequence:
                logger.debug(
                    "flows.subscriber.duplicate_sequence",
                    sequence=sequence,
                    channel=channel,
                )
                continue
            event_count += 1
            event_kind = message[:50]
            logger.debug("flows.stream.event", channel=channel, event_count=event_count, event_kind=event_kind)
            yield event

            if is_final_event(event):
                logger.debug("flows.stream.final", channel=channel)
                break

        logger.debug("flows.stream.ended", channel=channel, event_count=event_count)

    @override
    async def collect(
        self,
        task_id: str,
        timeout: float = 300.0,
        ready_event: asyncio.Event | None = None,
        *,
        after_sequence: int = 0,
    ) -> list[StreamEvent]:
        """
        Собирает все события до финального.

        Аргументы:
            task_id: ID задачи
            timeout: Таймаут ожидания в секундах
            ready_event: Event для сигнализации о готовности подписки
            after_sequence: reconnect cursor для live dedup

        Возвращает:
            Список всех событий
        """
        events: list[StreamEvent] = []
        async for event in self.subscribe(
            task_id,
            timeout=timeout,
            ready_event=ready_event,
            after_sequence=after_sequence,
        ):
            events.append(event)
        return events


RedisSubscriber = EventSubscriber


__all__ = [
    "EventSubscriber",
    "RedisSubscriber",
    "parse_event",
    "is_final_event",
]
