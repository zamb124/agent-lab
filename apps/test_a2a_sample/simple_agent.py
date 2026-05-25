"""
Упрощенный агент для тестов без зависимостей от core/agents.
Работает полностью автономно в InMemory режиме.
"""

from collections.abc import Sequence
from typing import Protocol, override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact,
    Part,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from core.types import JsonObject


class A2ATestTool(Protocol):
    async def execute(self, args: JsonObject, state: JsonObject | None) -> str: ...


class SimpleTestAgent(AgentExecutor):
    """Простой тестовый агент без зависимостей."""

    def __init__(self, *, tools: Sequence[A2ATestTool]) -> None:
        self.tools: tuple[A2ATestTool, ...] = tuple(tools)

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Выполняет агента и возвращает простой ответ."""
        content = context.get_user_input()

        # Простая логика: вызываем первый tool если есть
        if self.tools:
            tool_args: JsonObject = {}
            response = f"Tool result: {await self.tools[0].execute(tool_args, state=None)}"
        else:
            response = f"Echo: {content}"

        # Отправляем событие с ответом
        task_id = context.task_id
        context_id = context.context_id
        if task_id is None or context_id is None:
            raise ValueError("A2A RequestContext must contain task_id and context_id")

        # Создаем артифакт с ответом
        artifact = Artifact(
            artifact_id="response",
            parts=[Part(root=TextPart(text=response))],
            name="response",
        )

        # Отправляем артифакт
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=artifact,
                append=False,
            )
        )

        # Отправляем статус completed
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.completed),
                final=True,
            )
        )

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Отменяет выполнение."""
        task_id = context.task_id
        context_id = context.context_id
        if task_id is None or context_id is None:
            raise ValueError("A2A RequestContext must contain task_id and context_id")
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.canceled),
                final=True,
            )
        )
