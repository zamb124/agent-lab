"""
In-memory реализации Emitter и Subscriber.

Используются для внешних агентов, которые не требуют Redis.
"""

from collections.abc import AsyncIterator
from typing import override

from core.state import ExecutionState

from .base import BaseEmitter, BaseSubscriber, StreamEvent


class InMemoryEmitter(BaseEmitter):
    """
    In-memory Emitter - хранит события в списке.

    Используется для внешних агентов, которые не требуют Redis Pub/Sub.
    События можно получить через свойство `events`.

    Примеры:
        >>> emitter = InMemoryEmitter(state)
        >>> await emitter.emit_text("Hello")
        >>> print(emitter.events)  # [TaskArtifactUpdateEvent(...)]
    """

    _events: list[StreamEvent]

    def __init__(self, state: ExecutionState):
        super().__init__(state)
        self._events = []

    @property
    def events(self) -> list[StreamEvent]:
        """Возвращает все опубликованные события."""
        return self._events

    def clear(self) -> None:
        """Очищает список событий."""
        self._events.clear()

    @override
    async def _publish(self, event: StreamEvent) -> None:
        """Сохраняет событие в список."""
        self._events.append(event)


class InMemorySubscriber(BaseSubscriber):
    """
    In-memory Subscriber - читает события из InMemoryEmitter.

    Используется для тестов и внешних агентов.
    """

    _emitter: InMemoryEmitter

    def __init__(self, emitter: InMemoryEmitter):
        self._emitter = emitter

    @override
    async def subscribe(
        self,
        task_id: str,
        timeout: float = 300.0,
    ) -> AsyncIterator[StreamEvent]:
        """Возвращает события из emitter."""
        for event in self._emitter.events:
            yield event


__all__ = ["InMemoryEmitter", "InMemorySubscriber"]
