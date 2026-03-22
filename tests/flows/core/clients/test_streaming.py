"""
Тесты streaming: EventEmitter, EventSubscriber и is_final_event.

Проверяет корректную обработку финальных событий и синхронизацию подписки.
"""

import asyncio

import uuid

import pytest
from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.artifact import new_text_artifact
from a2a.utils.message import new_agent_text_message

from apps.flows.src.streaming.subscriber import is_final_event, TERMINAL_STATES


class TestIsFinalEvent:
    """Тесты для is_final_event()."""

    def test_completed_final_is_final(self):
        """state=completed + final=True -> финальное событие."""
        event = TaskStatusUpdateEvent(
            contextId="ctx",
            taskId="task",
            status=TaskStatus(state=TaskState.completed),
            final=True,
        )
        assert is_final_event(event) is True

    def test_failed_final_is_final(self):
        """state=failed + final=True -> финальное событие."""
        event = TaskStatusUpdateEvent(
            contextId="ctx",
            taskId="task",
            status=TaskStatus(state=TaskState.failed),
            final=True,
        )
        assert is_final_event(event) is True

    def test_input_required_final_is_final(self):
        """state=input-required + final=True -> финальное событие."""
        event = TaskStatusUpdateEvent(
            contextId="ctx",
            taskId="task",
            status=TaskStatus(state=TaskState.input_required),
            final=True,
        )
        assert is_final_event(event) is True

    def test_canceled_final_is_final(self):
        """state=canceled + final=True -> финальное событие."""
        event = TaskStatusUpdateEvent(
            contextId="ctx",
            taskId="task",
            status=TaskStatus(state=TaskState.canceled),
            final=True,
        )
        assert is_final_event(event) is True

    def test_working_final_is_not_final(self):
        """state=working + final=True -> НЕ финальное событие.
        
        Это ключевой тест! При tool_call LLM эмитит working+final=True,
        но агент продолжает работу после выполнения tool.
        """
        event = TaskStatusUpdateEvent(
            contextId="ctx",
            taskId="task",
            status=TaskStatus(state=TaskState.working),
            final=True,
        )
        assert is_final_event(event) is False

    def test_working_not_final_is_not_final(self):
        """state=working + final=False -> НЕ финальное событие."""
        event = TaskStatusUpdateEvent(
            contextId="ctx",
            taskId="task",
            status=TaskStatus(state=TaskState.working),
            final=False,
        )
        assert is_final_event(event) is False

    def test_completed_not_final_is_not_final(self):
        """state=completed + final=False -> НЕ финальное событие."""
        event = TaskStatusUpdateEvent(
            contextId="ctx",
            taskId="task",
            status=TaskStatus(state=TaskState.completed),
            final=False,
        )
        assert is_final_event(event) is False

    def test_artifact_update_is_not_final(self):
        """TaskArtifactUpdateEvent никогда не финальное."""
        from a2a.types import Artifact, Part, TextPart
        
        artifact = Artifact(
            artifactId="test-id",
            parts=[Part(root=TextPart(text="test"))],
        )
        event = TaskArtifactUpdateEvent(
            contextId="ctx",
            taskId="task",
            artifact=artifact,
            append=True,
            last_chunk=True,  # last_chunk НЕ означает финал stream!
        )
        assert is_final_event(event) is False

    def test_terminal_states_constant(self):
        """Проверяем что все терминальные состояния учтены."""
        assert "completed" in TERMINAL_STATES
        assert "failed" in TERMINAL_STATES
        assert "canceled" in TERMINAL_STATES
        assert "input-required" in TERMINAL_STATES
        assert "working" not in TERMINAL_STATES
        assert "submitted" not in TERMINAL_STATES


@pytest.mark.real_taskiq
class TestStreamingWithToolCalls:
    """Интеграционные тесты streaming с tool calls. Реальный Redis."""

    @pytest.fixture
    def redis_client(self):
        """Создает Redis клиент для тестов."""
        from core.clients import RedisClient
        from apps.flows.config import get_settings
        
        settings = get_settings()
        return RedisClient(settings.database.redis_url)

    @pytest.mark.asyncio
    async def test_subscriber_continues_after_working_final(self, redis_client):
        """
        Подписчик НЕ прекращает подписку при working+final=True.
        
        Сценарий:
        1. LLM решает вызвать tool -> working + final=True
        2. Tool выполняется
        3. LLM отвечает -> completed + final=True
        
        Подписчик должен дождаться completed, а не прекратить на working.
        """
        from a2a.types import Artifact, Part, TextPart
        from apps.flows.src.streaming import Emitter, EventSubscriber
        from core.state import ExecutionState
        
        await redis_client.connect()
        
        task_id = "test-tool-call-flow"
        context_id = "test-context"
        
        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=f"test-agent:{context_id}"
        )
        emitter = Emitter(redis_client, state)
        subscriber = EventSubscriber(redis_client)
        
        ready_event = asyncio.Event()
        collected_events = []
        
        async def collect():
            async for event in subscriber.subscribe(task_id, timeout=5.0, ready_event=ready_event):
                collected_events.append(event)
        
        async def emit_sequence():
            await ready_event.wait()
            await asyncio.sleep(0.05)
            
            # 1. Промежуточное событие: tool call (working + final=True)
            tool_call_msg = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[Part(root=TextPart(text="Calling tool..."))],
                metadata={"tool_calls": [{"id": "call_1", "name": "calculator"}]},
            )
            await emitter.emit(TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                status=TaskStatus(state=TaskState.working, message=tool_call_msg),
                final=True,  # Раньше это прекращало подписку!
            ))
            
            # 2. Текстовые чанки от LLM
            artifact1 = Artifact(
                artifactId="art1",
                parts=[Part(root=TextPart(text="Result: "))],
            )
            await emitter.emit(TaskArtifactUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                artifact=artifact1,
                append=True,
                last_chunk=False,
            ))
            
            artifact2 = Artifact(
                artifactId="art2",
                parts=[Part(root=TextPart(text="42"))],
            )
            await emitter.emit(TaskArtifactUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                artifact=artifact2,
                append=True,
                last_chunk=True,
            ))
            
            # 3. Финальное событие (completed + final=True)
            await emitter.emit(TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                status=TaskStatus(state=TaskState.completed, message=new_agent_text_message("Done")),
                final=True,
            ))
        
        try:
            await asyncio.gather(collect(), emit_sequence())
            
            # Проверяем что получили ВСЕ события, а не только первое
            assert len(collected_events) == 4
            
            # Первое - working (tool call)
            assert isinstance(collected_events[0], TaskStatusUpdateEvent)
            assert collected_events[0].status.state == TaskState.working
            
            # Второе и третье - artifact updates
            assert isinstance(collected_events[1], TaskArtifactUpdateEvent)
            assert isinstance(collected_events[2], TaskArtifactUpdateEvent)
            
            # Последнее - completed (финальное)
            assert isinstance(collected_events[3], TaskStatusUpdateEvent)
            assert collected_events[3].status.state == TaskState.completed
            assert collected_events[3].final is True
        finally:
            await redis_client.close()

