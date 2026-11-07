"""
Тесты reasoning событий в LLM streaming.
"""

import json
import uuid

import pytest
from a2a.helpers.proto_helpers import get_message_text
from a2a.types import (
    Artifact,
    Message,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.types.a2a_pb2 import ROLE_AGENT, ROLE_USER, TASK_STATE_FAILED, Role
from pydantic import BaseModel, ConfigDict, Field

from core.a2a import get_part_text, make_task_status, part_has_text
from core.a2a.task_projection import build_task_projection
from core.clients.llm import MockLLM, setup_mock_responses
from tests.fixtures.billing import make_test_billing_service


def _msg(text: str, role: Role = ROLE_USER) -> Message:
    """Создаёт A2A Message для тестов."""
    return Message(
        message_id=str(uuid.uuid4()),
        role=role,
        parts=[Part(text=text)],
    )


def _completed_status(task_id: str, context_id: str) -> TaskStatusUpdateEvent:
    return TaskStatusUpdateEvent(
        context_id=context_id,
        task_id=task_id,
        status=make_task_status(TaskState.TASK_STATE_COMPLETED),
    )


def _build_task_from_events(
    events: list[TaskArtifactUpdateEvent | TaskStatusUpdateEvent],
    task_id: str,
    context_id: str,
    input_message: Message,
) -> Task:
    """Lossless Task materialization — same reducer as GetTask / blocking SendMessage."""
    return build_task_projection(
        events=events,
        task_id=task_id,
        context_id=context_id,
        history=[input_message],
    )


class TestReasoningArtifactsInBuildTask:
    """Тесты reasoning артефактов в TaskProjectionAccumulator."""

    def test_build_task_separates_reasoning_and_response(self):
        """build_task_projection разделяет reasoning и response артефакты."""
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        input_message = _msg("Test question")
        reasoning_artifact_id = str(uuid.uuid4())
        response_artifact_id = str(uuid.uuid4())

        events = [
            TaskArtifactUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                artifact=Artifact(
                    artifact_id=reasoning_artifact_id,
                    name="reasoning",
                    parts=[Part(text="Step 1: ")]
                ),
                append=True,
                last_chunk=False,
            ),
            TaskArtifactUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                artifact=Artifact(
                    artifact_id=reasoning_artifact_id,
                    name="reasoning",
                    parts=[Part(text="analyzing...")]
                ),
                append=True,
                last_chunk=False,
            ),
            TaskArtifactUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                artifact=Artifact(
                    artifact_id=response_artifact_id,
                    name="response",
                    parts=[Part(text="Response text")]
                ),
                append=True,
                last_chunk=False,
            ),
            _completed_status(task_id, context_id),
        ]

        task = _build_task_from_events(events, task_id, context_id, input_message)

        assert task.artifacts is not None
        assert len(task.artifacts) == 2

        reasoning_artifact = next((a for a in task.artifacts if a.name == "reasoning"), None)
        response_artifact = next((a for a in task.artifacts if a.name == "response"), None)

        assert reasoning_artifact is not None
        assert response_artifact is not None

        reasoning_text = "".join(get_part_text(p) for p in reasoning_artifact.parts if part_has_text(p))
        assert reasoning_text == "Step 1: analyzing..."

        response_text = "".join(get_part_text(p) for p in response_artifact.parts if part_has_text(p))
        assert response_text == "Response text"

    def test_build_task_with_reasoning_only(self):
        """build_task_projection обрабатывает только reasoning артефакты."""
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        input_message = _msg("Test question")

        events = [
            TaskArtifactUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                artifact=Artifact(
                    artifact_id=str(uuid.uuid4()),
                    name="reasoning",
                    parts=[Part(text="Thinking...")]
                ),
                append=True,
                last_chunk=True,
            ),
            _completed_status(task_id, context_id),
        ]

        task = _build_task_from_events(events, task_id, context_id, input_message)

        assert task.artifacts is not None
        assert len(task.artifacts) == 1

        reasoning_artifact = task.artifacts[0]
        assert reasoning_artifact.name == "reasoning"

        reasoning_text = "".join(get_part_text(p) for p in reasoning_artifact.parts if part_has_text(p))
        assert reasoning_text == "Thinking..."

    def test_failed_status_preserves_error_message_with_reasoning_artifact(self):
        """При failed и артефакте reasoning текст ошибки остаётся в status.message (для A2A-клиента)."""
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        input_message = _msg("Test question")

        events = [
            TaskArtifactUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                artifact=Artifact(
                    artifact_id=str(uuid.uuid4()),
                    name="reasoning",
                    parts=[Part(text="partial stream")],
                ),
                append=True,
                last_chunk=False,
            ),
            TaskStatusUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                status=TaskStatus(
                    state=TASK_STATE_FAILED,
                    message=Message(message_id="msg", role=ROLE_AGENT, parts=[Part(text="httpx2.ReadTimeout")]),
                ),
            ),
        ]

        task = _build_task_from_events(events, task_id, context_id, input_message)

        assert task.status.state == TASK_STATE_FAILED
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
            and e.artifact.name != "reasoning"
        ]

        assert len(reasoning_events) > 0, "Должны быть reasoning артефакты"
        assert len(response_events) > 0, "Должны быть response артефакты"

        reasoning_text = ""
        for event in reasoning_events:
            for part in event.artifact.parts:
                if part_has_text(part):
                    reasoning_text += get_part_text(part)

        assert "Step 1: thinking..." in reasoning_text
        assert "Step 2: analyzing..." in reasoning_text

        response_text = ""
        for event in response_events:
            for part in event.artifact.parts:
                if part_has_text(part):
                    response_text += get_part_text(part)

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
                if part_has_text(part):
                    reasoning_text += get_part_text(part)

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
            ],
        billing_service=make_test_billing_service())

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
                if part_has_text(part):
                    reasoning_text += get_part_text(part)

        assert reasoning_text == "Reasoning text"

    @pytest.mark.asyncio
    async def test_mock_llm_chat_structured_output_ignores_reasoning_artifacts(self):
        """chat(response_model=...) парсит только основной контент, без префикса reasoning."""

        class _Gen(BaseModel):
            model_config = ConfigDict(extra="forbid")

            code: str = Field(..., min_length=1)

        mock = MockLLM()
        body = {"code": 'async def run(args, state):\n    return {"ok": true}'}
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
            [{"role": "ROLE_USER", "content": "сделай run"}],
            response_model=_Gen,
        )
        assert out.code == body["code"]
