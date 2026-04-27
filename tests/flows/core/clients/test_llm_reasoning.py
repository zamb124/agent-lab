"""
Тесты reasoning событий в LLM streaming.
"""

import json
import uuid

import pytest
from pydantic import BaseModel, ConfigDict, Field
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.message import get_message_text, new_agent_text_message

from apps.flows.src.channels.a2a import _build_task_from_events
from core.clients.llm import MockLLM, setup_mock_responses


def _msg(text: str, role: Role = Role.user) -> Message:
    """Создаёт A2A Message для тестов."""
    return Message(
        messageId=str(uuid.uuid4()),
        role=role,
        parts=[Part(root=TextPart(text=text))],
    )


class TestReasoningArtifactsInBuildTask:
    """Тесты reasoning артефактов в _build_task_from_events."""

    @pytest.mark.asyncio
    async def test_build_task_separates_reasoning_and_response(self, app):
        """_build_task_from_events разделяет reasoning и response артефакты."""
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        input_message = _msg("Test question")

        events = [
            TaskArtifactUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                artifact=Artifact(
                    artifactId=str(uuid.uuid4()),
                    name="reasoning",
                    parts=[Part(root=TextPart(text="Step 1: "))]
                ),
                append=True,
                last_chunk=False,
            ),
            TaskArtifactUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                artifact=Artifact(
                    artifactId=str(uuid.uuid4()),
                    name="reasoning",
                    parts=[Part(root=TextPart(text="analyzing..."))]
                ),
                append=True,
                last_chunk=False,
            ),
            TaskArtifactUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                artifact=Artifact(
                    artifactId=str(uuid.uuid4()),
                    parts=[Part(root=TextPart(text="Response text"))]
                ),
                append=True,
                last_chunk=False,
            ),
        ]

        task = await _build_task_from_events(events, task_id, context_id, input_message, flow_id="test_flow")

        assert task.artifacts is not None
        assert len(task.artifacts) == 2

        reasoning_artifact = next((a for a in task.artifacts if a.name == "reasoning"), None)
        response_artifact = next((a for a in task.artifacts if a.name == "response"), None)

        assert reasoning_artifact is not None
        assert response_artifact is not None

        reasoning_text = "".join(p.root.text for p in reasoning_artifact.parts if hasattr(p.root, "text"))
        assert reasoning_text == "Step 1: analyzing..."

        response_text = "".join(p.root.text for p in response_artifact.parts if hasattr(p.root, "text"))
        assert response_text == "Response text"

    @pytest.mark.asyncio
    async def test_build_task_with_reasoning_only(self, app):
        """_build_task_from_events обрабатывает только reasoning артефакты."""
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        input_message = _msg("Test question")

        events = [
            TaskArtifactUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                artifact=Artifact(
                    artifactId=str(uuid.uuid4()),
                    name="reasoning",
                    parts=[Part(root=TextPart(text="Thinking..."))]
                ),
                append=True,
                last_chunk=True,
            ),
        ]

        task = await _build_task_from_events(events, task_id, context_id, input_message, flow_id="test_flow")

        assert task.artifacts is not None
        assert len(task.artifacts) == 1

        reasoning_artifact = task.artifacts[0]
        assert reasoning_artifact.name == "reasoning"

        reasoning_text = "".join(p.root.text for p in reasoning_artifact.parts if hasattr(p.root, "text"))
        assert reasoning_text == "Thinking..."

    @pytest.mark.asyncio
    async def test_failed_status_preserves_error_message_with_reasoning_artifact(self, app):
        """При failed и артефакте reasoning текст ошибки остаётся в status.message (для A2A-клиента)."""
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        input_message = _msg("Test question")

        events = [
            TaskArtifactUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                artifact=Artifact(
                    artifactId=str(uuid.uuid4()),
                    name="reasoning",
                    parts=[Part(root=TextPart(text="partial stream"))],
                ),
                append=True,
                last_chunk=False,
            ),
            TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                status=TaskStatus(
                    state=TaskState.failed,
                    message=new_agent_text_message("httpx.ReadTimeout"),
                ),
                final=True,
            ),
        ]

        task = await _build_task_from_events(events, task_id, context_id, input_message, flow_id="test_flow")

        assert task.status.state == TaskState.failed
        assert task.status.message is not None
        assert "ReadTimeout" in get_message_text(task.status.message)


class TestMockLLMReasoning:
    """Тесты reasoning в MockLLM streaming."""

    @pytest.mark.asyncio
    async def test_mock_llm_streams_reasoning_artifacts(self):
        """MockLLM стримит reasoning как отдельные артефакты с name='reasoning'."""
        mock = MockLLM()
        mock.configure(
            response_queue=[
                {
                    "type": "text",
                    "content": "Response text",
                    "reasoning": "Step 1: thinking... Step 2: analyzing...",
                }
            ]
        )

        events = []
        async for event in mock.stream([_msg("Test question")]):
            events.append(event)

        reasoning_events = [
            e
            for e in events
            if isinstance(e, TaskArtifactUpdateEvent) and e.artifact.name == "reasoning"
        ]
        response_events = [
            e
            for e in events
            if isinstance(e, TaskArtifactUpdateEvent)
            and (e.artifact.name is None or e.artifact.name == "response")
        ]

        assert len(reasoning_events) > 0, "Должны быть reasoning артефакты"
        assert len(response_events) > 0, "Должны быть response артефакты"

        reasoning_text = ""
        for event in reasoning_events:
            for part in event.artifact.parts:
                if hasattr(part.root, "text"):
                    reasoning_text += part.root.text

        assert "Step 1: thinking..." in reasoning_text
        assert "Step 2: analyzing..." in reasoning_text

        response_text = ""
        for event in response_events:
            for part in event.artifact.parts:
                if hasattr(part.root, "text"):
                    response_text += part.root.text

        assert response_text == "Response text"

    @pytest.mark.asyncio
    async def test_mock_llm_reasoning_only(self):
        """MockLLM работает только с reasoning без content."""
        mock = MockLLM()
        mock.configure(
            response_queue=[
                {
                    "type": "text",
                    "content": "",
                    "reasoning": "Just reasoning",
                }
            ]
        )

        events = []
        async for event in mock.stream([_msg("Test")]):
            events.append(event)

        reasoning_events = [
            e
            for e in events
            if isinstance(e, TaskArtifactUpdateEvent) and e.artifact.name == "reasoning"
        ]

        assert len(reasoning_events) > 0

        reasoning_text = ""
        for event in reasoning_events:
            for part in event.artifact.parts:
                if hasattr(part.root, "text"):
                    reasoning_text += part.root.text

        assert reasoning_text == "Just reasoning"

    @pytest.mark.asyncio
    async def test_setup_mock_responses_with_reasoning(self):
        """setup_mock_responses поддерживает reasoning в response_queue."""
        mock = setup_mock_responses(
            response_queue=[
                {
                    "type": "text",
                    "content": "Answer",
                    "reasoning": "Reasoning text",
                }
            ]
        )

        events = []
        async for event in mock.stream([_msg("Question")]):
            events.append(event)

        reasoning_events = [
            e
            for e in events
            if isinstance(e, TaskArtifactUpdateEvent) and e.artifact.name == "reasoning"
        ]

        assert len(reasoning_events) > 0

        reasoning_text = ""
        for event in reasoning_events:
            for part in event.artifact.parts:
                if hasattr(part.root, "text"):
                    reasoning_text += part.root.text

        assert reasoning_text == "Reasoning text"

    @pytest.mark.asyncio
    async def test_mock_llm_chat_structured_output_ignores_reasoning_artifacts(self):
        """chat(response_model=...) парсит только основной контент, без префикса reasoning."""

        class _Gen(BaseModel):
            model_config = ConfigDict(extra="forbid")

            code: str = Field(..., min_length=1)

        mock = MockLLM()
        body = {"code": 'async def run(state):\n    return {"ok": true}'}
        mock.configure(
            response_queue=[
                {
                    "type": "text",
                    "content": json.dumps(body, ensure_ascii=False),
                    "reasoning": "Пользователь просит сгенерировать код...",
                }
            ]
        )

        out = await mock.chat(
            [{"role": "user", "content": "сделай run"}],
            response_model=_Gen,
        )
        assert out.code == body["code"]
