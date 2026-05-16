"""
In-memory реализации Emitter и Subscriber.

Используются для внешних агентов, которые не требуют Redis.
"""

from typing import Any
from collections.abc import AsyncIterator

from core.state import ExecutionState

from .base import BaseEmitter, BaseSubscriber, StreamEvent


class InMemoryEmitter(BaseEmitter):
    """
    In-memory Emitter - хранит события в списке.

    Используется для внешних агентов, которые не требуют Redis Pub/Sub.
    События можно получить через свойство `events`.

    Examples:
        >>> emitter = InMemoryEmitter(state)
        >>> await emitter.emit_text("Hello")
        >>> print(emitter.events)  # [TaskArtifactUpdateEvent(...)]
    """

    def __init__(self, state: ExecutionState):
        super().__init__(state)
        self._events: list[Any] = []

    @property
    def events(self) -> list[Any]:
        """Возвращает все опубликованные события."""
        return self._events

    def clear(self) -> None:
        """Очищает список событий."""
        self._events.clear()

    async def _publish(self, event: Any) -> None:
        """Сохраняет событие в список."""
        self._events.append(event)


class InMemorySubscriber(BaseSubscriber):
    """
    In-memory Subscriber - читает события из InMemoryEmitter.

    Используется для тестов и внешних агентов.
    """

    def __init__(self, emitter: InMemoryEmitter):
        self._emitter = emitter

    async def subscribe(
        self,
        task_id: str,
        timeout: float = 300.0,
    ) -> AsyncIterator[StreamEvent]:
        """Возвращает события из emitter."""
        for event in self._emitter.events:
            yield event


__all__ = ["InMemoryEmitter", "InMemorySubscriber"]

