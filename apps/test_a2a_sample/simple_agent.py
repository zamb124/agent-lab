"""
Упрощенный агент для тестов без зависимостей от core/agents.
Работает полностью автономно в InMemory режиме.
"""

from typing import Any

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
from a2a.utils.message import get_message_text


class SimpleTestAgent(AgentExecutor):
    """Простой тестовый агент без зависимостей."""

    def __init__(self, tools: list[Any] | None = None, prompt: str = ""):
        self.tools = tools if tools is not None else []
        self.prompt = prompt

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """Выполняет агента и возвращает простой ответ."""
        # Получаем входное сообщение
        user_input = context.get_user_input()
        if isinstance(user_input, str):
            content = user_input
        else:
            content = get_message_text(user_input)

        # Простая логика: вызываем первый tool если есть
        response = ""
        if self.tools:
            tool = self.tools[0]
            try:
                result = await tool.execute({}, state=None)
                response = f"Tool result: {result}"
            except Exception as e:
                response = f"Tool error: {e}"
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
                append=False
            )
        )

        # Отправляем статус completed
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.completed),
                final=True
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        """Отменяет выполнение."""
        pass
