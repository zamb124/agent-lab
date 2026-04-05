"""
Тесты LLM клиента.

MockLLM для тестов - stream-first архитектура с A2A событиями.
"""

import uuid

import pytest
from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)

from core.clients.llm import MockLLM, setup_mock_responses


def _msg(text: str, role: Role = Role.user) -> Message:
    """Создаёт A2A Message для тестов."""
    return Message(
        messageId=str(uuid.uuid4()),
        role=role,
        parts=[Part(root=TextPart(text=text))],
    )


class TestMockLLMStreaming:
    """Тесты стриминга в MockLLM."""

    @pytest.mark.asyncio
    async def test_stream_yields_artifact_events(self):
        """stream yield'ит TaskArtifactUpdateEvent по токенам как реальная LLM."""
        mock = MockLLM()
        mock.configure(default_response="Hello world!")

        events = []
        async for event in mock.stream([_msg("Hi")]):
            events.append(event)

        artifact_events = [e for e in events if isinstance(e, TaskArtifactUpdateEvent)]
        
        # Стримит по токенам (2-5 символов) - несколько чанков
        assert len(artifact_events) > 1
        
        # Собираем полный текст из чанков
        full_text = "".join(e.artifact.parts[0].root.text for e in artifact_events)
        assert full_text == "Hello world!"
        
        # Последний чанк помечен как last_chunk
        assert artifact_events[-1].last_chunk is True
        # Промежуточные чанки не last
        for event in artifact_events[:-1]:
            assert event.last_chunk is False

    @pytest.mark.asyncio
    async def test_stream_yields_final_status_event(self):
        """stream yield'ит завершающий TaskStatusUpdateEvent (completed; final=False как в LLMClient)."""
        mock = MockLLM()
        mock.configure(default_response="Test response")

        events = []
        async for event in mock.stream([_msg("Hi")]):
            events.append(event)

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        completed = [e for e in status_events if e.status.state.value == "completed"]
        assert len(completed) == 1
        assert completed[0].final is False

    @pytest.mark.asyncio
    async def test_stream_with_response_queue(self):
        """stream работает с очередью ответов."""
        mock = MockLLM()
        mock.configure(
            response_queue=[
                {"type": "text", "content": "First response"},
                {"type": "text", "content": "Second response"},
            ]
        )

        # Первый вызов
        content1 = ""
        async for event in mock.stream([_msg("Q1")]):
            if isinstance(event, TaskArtifactUpdateEvent):
                content1 += event.artifact.parts[0].root.text
        assert content1 == "First response"

        # Второй вызов
        content2 = ""
        async for event in mock.stream([_msg("Q2")]):
            if isinstance(event, TaskArtifactUpdateEvent):
                content2 += event.artifact.parts[0].root.text
        assert content2 == "Second response"

    @pytest.mark.asyncio
    async def test_stream_tool_call_yields_status_event(self):
        """stream yield'ит TaskStatusUpdateEvent для tool call."""
        mock = MockLLM()
        mock.configure(
            response_queue=[{"type": "tool_call", "tool": "calculator", "args": {"x": 1}}]
        )

        events = []
        async for event in mock.stream([_msg("calc")]):
            events.append(event)

        # Tool call должен вернуть TaskStatusUpdateEvent с tool_calls в metadata
        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        tool_call_events = [
            e
            for e in status_events
            if e.status.message and e.status.message.metadata and "tool_calls" in e.status.message.metadata
        ]
        assert len(tool_call_events) == 1

    @pytest.mark.asyncio
    async def test_stream_includes_task_id_context_id(self):
        """stream включает taskId и contextId в события."""
        mock = MockLLM()
        mock.configure(default_response="Test")

        task_id = "test-task-123"
        context_id = "test-context-456"

        async for event in mock.stream([_msg("Hi")], task_id=task_id, context_id=context_id):
            assert event.task_id == task_id
            assert event.context_id == context_id


class TestSetupMockResponses:
    """Тесты helper функции setup_mock_responses."""

    @pytest.mark.asyncio
    async def test_setup_returns_configured_mock(self):
        """setup_mock_responses возвращает настроенный mock."""
        mock = setup_mock_responses(default_response="Configured!")

        content = ""
        async for event in mock.stream([_msg("test")]):
            if isinstance(event, TaskArtifactUpdateEvent):
                content += event.artifact.parts[0].root.text

        assert content == "Configured!"

    @pytest.mark.asyncio
    async def test_setup_with_response_queue(self):
        """setup_mock_responses с очередью ответов."""
        mock = setup_mock_responses(
            response_queue=[
                {"type": "text", "content": "Queued response"},
            ]
        )

        content = ""
        async for event in mock.stream([_msg("test")]):
            if isinstance(event, TaskArtifactUpdateEvent):
                content += event.artifact.parts[0].root.text

        assert content == "Queued response"

    @pytest.mark.asyncio
    async def test_setup_with_tool_responses(self):
        """setup_mock_responses с tool ответами."""
        mock = setup_mock_responses(
            tool_responses={"calc": {"tool": "calculator", "args": {"expr": "2+2"}}}
        )

        events = []
        async for event in mock.stream([_msg("calc something")]):
            events.append(event)

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        tool_events = [
            e
            for e in status_events
            if e.status.message and e.status.message.metadata and "tool_calls" in e.status.message.metadata
        ]
        assert len(tool_events) == 1
