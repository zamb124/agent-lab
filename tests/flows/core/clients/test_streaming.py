"""
Тесты streaming: EventEmitter, EventSubscriber и is_final_event.

Проверяет корректную обработку финальных событий и синхронизацию подписки.
"""

import asyncio
import uuid
from typing import cast

import pytest
from a2a.helpers.proto_helpers import new_text_part
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
from a2a.types.a2a_pb2 import (
    ROLE_AGENT,
    TASK_STATE_CANCELED,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
    TASK_STATE_INPUT_REQUIRED,
    TASK_STATE_SUBMITTED,
    TASK_STATE_WORKING,
)

from apps.flows.config import get_settings
from apps.flows.src.a2a import A2ATaskProjectionService
from apps.flows.src.models.a2a_projection import A2ATaskProjection
from apps.flows.src.state import ExecutionState
from apps.flows.src.streaming import Emitter, EventSubscriber, InMemoryEmitter, StreamEvent
from apps.flows.src.streaming.subscriber import is_final_event
from core.a2a import TERMINAL_A2A_TASK_STATES, mapping_from_struct, struct_from_mapping
from core.clients.redis_client import RedisClient
from core.types import JsonObject


def _status_event(
    *,
    state: int,
    context_id: str = "ctx",
    task_id: str = "task",
    metadata: JsonObject | None = None,
    message: Message | None = None,
) -> TaskStatusUpdateEvent:
    status = TaskStatus(state=cast(TaskState, state))
    if message is not None:
        status.message.CopyFrom(message)
    event = TaskStatusUpdateEvent(
        context_id=context_id,
        task_id=task_id,
        status=status,
    )
    if metadata:
        event.metadata.CopyFrom(struct_from_mapping(metadata))
    return event


class TestIsFinalEvent:
    """Тесты для is_final_event()."""

    def test_completed_is_final(self):
        """TASK_STATE_COMPLETED -> финальное событие."""
        assert is_final_event(_status_event(state=TASK_STATE_COMPLETED)) is True

    def test_failed_is_final(self):
        """TASK_STATE_FAILED -> финальное событие."""
        assert is_final_event(_status_event(state=TASK_STATE_FAILED)) is True

    def test_input_required_is_final(self):
        """TASK_STATE_INPUT_REQUIRED -> финальное событие."""
        assert is_final_event(_status_event(state=TASK_STATE_INPUT_REQUIRED)) is True

    def test_canceled_is_final(self):
        """TASK_STATE_CANCELED -> финальное событие."""
        assert is_final_event(_status_event(state=TASK_STATE_CANCELED)) is True

    def test_working_is_not_final(self):
        """TASK_STATE_WORKING -> НЕ финальное (tool_call / ping)."""
        assert is_final_event(_status_event(state=TASK_STATE_WORKING)) is False

    @pytest.mark.asyncio
    async def test_ping_event_is_working_non_final(self):
        """Heartbeat идет как statusUpdate WORKING и не закрывает stream."""
        state = ExecutionState.create(
            task_id="task-ping",
            context_id="ctx-ping",
            user_id="test-user",
            session_id="test-agent:ctx-ping",
        )
        emitter = InMemoryEmitter(state)

        await emitter.emit_ping(sequence=7)

        assert len(emitter.events) == 1
        event = emitter.events[0]
        assert isinstance(event, TaskStatusUpdateEvent)
        assert event.status.state == TASK_STATE_WORKING
        meta = mapping_from_struct(event.metadata)
        assert meta["platform_ping"] is True
        assert meta["sequence"] == 7
        assert is_final_event(event) is False

    def test_artifact_update_is_not_final(self):
        """TaskArtifactUpdateEvent никогда не финальное."""
        artifact = Artifact(
            artifact_id="test-id",
            parts=[Part(text="test")],
        )
        event = TaskArtifactUpdateEvent(
            context_id="ctx",
            task_id="task",
            artifact=artifact,
            append=True,
            last_chunk=True,
        )
        assert is_final_event(event) is False

    def test_terminal_states_constant(self):
        """Проверяем что все терминальные состояния учтены."""
        assert TASK_STATE_COMPLETED in TERMINAL_A2A_TASK_STATES
        assert TASK_STATE_FAILED in TERMINAL_A2A_TASK_STATES
        assert TASK_STATE_CANCELED in TERMINAL_A2A_TASK_STATES
        assert TASK_STATE_WORKING not in TERMINAL_A2A_TASK_STATES
        assert TASK_STATE_SUBMITTED not in TERMINAL_A2A_TASK_STATES

    def test_agent_handoff_input_required_is_final(self):
        """Handoff pause: collect останавливается на input-required + handoff metadata."""
        event = _status_event(
            state=TASK_STATE_INPUT_REQUIRED,
            metadata={
                "platform_handoff_continue": True,
                "platform_interrupt": {
                    "body": {"kind": "handoff", "target_flow_id": "child_flow"},
                },
            },
        )
        assert is_final_event(event) is True

    def test_operator_task_input_required_is_final(self):
        """HITL operator_task: подписчик SendStreamingMessage закрывается."""
        event = _status_event(
            state=TASK_STATE_INPUT_REQUIRED,
            metadata={
                "platform_interrupt": {
                    "body": {"kind": "operator_task"},
                },
            },
        )
        assert is_final_event(event) is True

    def test_operator_task_input_required_final_even_when_legacy_continue_flag(self):
        """Legacy platform_handoff_continue на operator_task всё равно final (resubscribe)."""
        event = _status_event(
            state=TASK_STATE_INPUT_REQUIRED,
            metadata={
                "platform_handoff_continue": True,
                "platform_interrupt": {
                    "body": {"kind": "operator_task"},
                },
            },
        )
        assert is_final_event(event) is True


class TestInMemoryEmitterArtifacts:
    """Stable artifact identity follows a logical emitter stream."""

    @pytest.mark.asyncio
    async def test_text_chunks_share_artifact_id_until_last_chunk(self):
        state = ExecutionState.create(
            task_id="task-stable-artifact",
            context_id="context-stable-artifact",
            user_id="test-user",
            session_id="test-flow:context-stable-artifact",
        )
        emitter = InMemoryEmitter(state)

        await emitter.emit_text("first", artifact_name="response")
        await emitter.emit_text(
            "second",
            artifact_name="response",
            last_chunk=True,
        )
        await emitter.emit_text(
            "next logical response",
            artifact_name="response",
            last_chunk=True,
        )

        artifact_events = [
            event
            for event in emitter.events
            if isinstance(event, TaskArtifactUpdateEvent)
        ]
        assert artifact_events[0].artifact.artifact_id == artifact_events[1].artifact.artifact_id
        assert artifact_events[2].artifact.artifact_id != artifact_events[1].artifact.artifact_id
        assert [event.artifact.name for event in artifact_events] == [
            "response",
            "response",
            "response",
        ]


@pytest.mark.real_taskiq
class TestStreamingWithToolCalls:
    """Интеграционные тесты streaming с tool calls. Реальный Redis."""

    @pytest.fixture
    def redis_client(self) -> RedisClient:
        """Создает Redis клиент для тестов."""
        settings = get_settings()
        return RedisClient(settings.database.redis_url)

    @pytest.mark.asyncio
    async def test_subscriber_continues_after_working(
        self,
        redis_client: RedisClient,
    ) -> None:
        """
        Подписчик НЕ прекращает подписку при WORKING.

        Сценарий:
        1. LLM решает вызвать tool -> WORKING
        2. Tool выполняется
        3. LLM отвечает -> COMPLETED

        Подписчик должен дождаться COMPLETED, а не прекратить на WORKING.
        """
        await redis_client.connect()

        suffix = uuid.uuid4().hex
        task_id = f"test-tool-call-flow-{suffix}"
        context_id = f"test-context-{suffix}"

        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=f"test-agent:{context_id}",
        )
        projection_service = A2ATaskProjectionService(redis_client=redis_client)
        _ = await A2ATaskProjection.ensure_task(
            company_id="streaming-test-company",
            session_id=state.session_id,
            flow_id=state.session_flow_id,
            owner_user_id="streaming-test-user",
            task=Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TASK_STATE_SUBMITTED),
            ),
        )
        emitter = Emitter(
            projection_service,
            state,
            company_id="streaming-test-company",
        )
        subscriber = EventSubscriber(redis_client)

        ready_event = asyncio.Event()
        collected_events: list[StreamEvent] = []

        async def collect() -> None:
            async for event in subscriber.subscribe(task_id, timeout=5.0, ready_event=ready_event):
                collected_events.append(event)

        async def emit_sequence() -> None:
            _ = await ready_event.wait()
            await asyncio.sleep(0.05)

            tool_call_msg = Message(
                message_id=str(uuid.uuid4()),
                role=ROLE_AGENT,
                parts=[new_text_part("Calling tool...")],
            )
            tool_call_msg.metadata.CopyFrom(
                struct_from_mapping({"tool_calls": [{"id": "call_1", "name": "calculator"}]})
            )
            await emitter.emit(
                _status_event(
                    state=TASK_STATE_WORKING,
                    context_id=context_id,
                    task_id=task_id,
                    message=tool_call_msg,
                )
            )

            artifact1 = Artifact(
                artifact_id="art1",
                parts=[Part(text="Result: ")],
            )
            await emitter.emit(
                TaskArtifactUpdateEvent(
                    context_id=context_id,
                    task_id=task_id,
                    artifact=artifact1,
                    append=True,
                    last_chunk=False,
                )
            )

            artifact2 = Artifact(
                artifact_id="art2",
                parts=[Part(text="42")],
            )
            await emitter.emit(
                TaskArtifactUpdateEvent(
                    context_id=context_id,
                    task_id=task_id,
                    artifact=artifact2,
                    append=True,
                    last_chunk=True,
                )
            )

            done_msg = Message(
                message_id=str(uuid.uuid4()),
                role=ROLE_AGENT,
                parts=[Part(text="Done")],
            )
            await emitter.emit(
                _status_event(
                    state=TASK_STATE_COMPLETED,
                    context_id=context_id,
                    task_id=task_id,
                    message=done_msg,
                )
            )

        try:
            _ = await asyncio.gather(collect(), emit_sequence())

            assert len(collected_events) == 4

            assert isinstance(collected_events[0], TaskStatusUpdateEvent)
            assert collected_events[0].status.state == TASK_STATE_WORKING

            assert isinstance(collected_events[1], TaskArtifactUpdateEvent)
            assert isinstance(collected_events[2], TaskArtifactUpdateEvent)

            assert isinstance(collected_events[3], TaskStatusUpdateEvent)
            assert collected_events[3].status.state == TASK_STATE_COMPLETED
        finally:
            await redis_client.close()
