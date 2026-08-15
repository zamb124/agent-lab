"""
Тесты LLM клиента.

MockLLM для тестов - stream-first архитектура с A2A событиями.
"""

import uuid

import pytest
from a2a.types import Message, Part, TaskArtifactUpdateEvent, TaskState, TaskStatusUpdateEvent
from a2a.types.a2a_pb2 import ROLE_USER, Role

from core.a2a import get_part_text, mapping_from_struct
from core.clients.llm import MockLLM, setup_mock_responses
from core.clients.llm.mock import split_mock_stream_text


def test_split_mock_stream_text_keeps_multiple_chunks_without_tiny_tokens() -> None:
    chunks = split_mock_stream_text("Hello world!")
    assert len(chunks) > 1
    assert "".join(chunks) == "Hello world!"
    assert all(len(chunk) >= 2 for chunk in chunks)


def _msg(text: str, role: Role = ROLE_USER) -> Message:
    """Создаёт A2A Message для тестов."""
    return Message(
        message_id=str(uuid.uuid4()),
        role=role,
        parts=[Part(text=text)],
    )


def _status_message_metadata(event: TaskStatusUpdateEvent) -> dict[str, object]:
    message = event.status.message
    if message is None or not message.HasField("metadata"):
        return {}
    return mapping_from_struct(message.metadata)


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

        # Стримит заранее известный текст несколькими чанками
        assert len(artifact_events) > 1

        # Собираем полный текст из чанков
        full_text = "".join(get_part_text(e.artifact.parts[0]) for e in artifact_events)
        assert full_text == "Hello world!"

        # Последний чанк помечен как last_chunk
        assert artifact_events[-1].last_chunk is True
        # Промежуточные чанки не last
        for event in artifact_events[:-1]:
            assert event.last_chunk is False

    @pytest.mark.asyncio
    async def test_stream_yields_final_status_event(self):
        """stream yield'ит завершающий TaskStatusUpdateEvent (WORKING — не конец A2A-задачи)."""
        mock = MockLLM()
        mock.configure(default_response="Test response")

        events = []
        async for event in mock.stream([_msg("Hi")]):
            events.append(event)

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        assert status_events
        assert status_events[-1].status.state == TaskState.TASK_STATE_WORKING
        assert not any(
            event.status.state == TaskState.TASK_STATE_COMPLETED for event in status_events
        )

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
                content1 += get_part_text(event.artifact.parts[0])
        assert content1 == "First response"

        # Второй вызов
        content2 = ""
        async for event in mock.stream([_msg("Q2")]):
            if isinstance(event, TaskArtifactUpdateEvent):
                content2 += get_part_text(event.artifact.parts[0])
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
            if "tool_calls" in _status_message_metadata(e)
        ]
        assert len(tool_call_events) == 1

    @pytest.mark.asyncio
    async def test_stream_tool_call_emits_second_status_without_tool_calls(self):
        """Как LLMClient.stream: после статуса с tool_calls идёт второй статус (часто только usage)."""
        mock = MockLLM()
        mock.configure(
            response_queue=[{"type": "tool_call", "tool": "calculator", "args": {"x": 1}}]
        )

        events = []
        async for event in mock.stream([_msg("calc")]):
            events.append(event)

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        assert len(status_events) >= 2
        first_metadata = _status_message_metadata(status_events[0])
        assert "tool_calls" in first_metadata

        second_metadata = _status_message_metadata(status_events[1])
        if second_metadata:
            tc = second_metadata.get("tool_calls")
            assert tc is None or tc == []

        merged: list = []
        for event in status_events:
            metadata = _status_message_metadata(event)
            tool_calls = metadata.get("tool_calls")
            if tool_calls:
                merged = tool_calls
        assert merged

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
                content += get_part_text(event.artifact.parts[0])

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
                content += get_part_text(event.artifact.parts[0])

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
            if "tool_calls" in _status_message_metadata(e)
        ]
        assert len(tool_events) == 1
