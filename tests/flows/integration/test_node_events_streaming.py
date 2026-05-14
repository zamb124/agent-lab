"""
Тест стриминга событий нод.

Проверяет что Agent эмитит node_start/node_complete для каждой ноды.
Реальный Redis, реальный subscriber.
"""

import asyncio
import uuid

import pytest
from a2a.types import TaskArtifactUpdateEvent

from apps.flows.src.runtime.flow import Flow
from apps.flows.src.streaming import EventSubscriber
from core.state import ExecutionState


@pytest.mark.real_taskiq
class TestNodeEventsStreaming:
    """Интеграционные тесты стриминга событий нод."""

    @pytest.mark.asyncio
    async def test_function_node_emits_start_and_complete(self, container):
        """Function нода эмитит node_start и node_complete."""
        redis_client = container.redis_client
        await redis_client.connect()

        task_id = f"test-node-events-{uuid.uuid4()}"
        context_id = f"ctx-{uuid.uuid4()}"

        # Создаём агент с одной function нодой
        agent = await Flow.from_config({
            "id": "test_node_events_agent",
            "name": "Test Node Events",
            "entry": "process",
            "nodes": {
                "process": {
                    "type": "code",
                    "code": "async def run(state):\n    state['response'] = 'done'\n    return state",
                },
            },
            "edges": [{"from": "process", "to": None}],
        })

        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=f"test-agent:{context_id}",
            content="test input",
        )

        subscriber = EventSubscriber(redis_client)
        ready_event = asyncio.Event()
        collected_events = []

        async def collect():
            async for event in subscriber.subscribe(task_id, timeout=5.0, ready_event=ready_event):
                collected_events.append(event)
                # Ждём только artifact events (node_start, node_complete)
                if len(collected_events) >= 2:
                    break

        async def execute():
            await ready_event.wait()
            await asyncio.sleep(0.05)
            await agent.run(state)

        try:
            # Запускаем подписку и выполнение параллельно
            await asyncio.wait_for(
                asyncio.gather(collect(), execute()),
                timeout=10.0
            )

            # Проверяем события
            assert len(collected_events) >= 2

            # Первое - node_start
            start_event = collected_events[0]
            assert isinstance(start_event, TaskArtifactUpdateEvent)
            assert start_event.artifact.name == "node_start_process"

            # Второе - node_complete
            complete_event = collected_events[1]
            assert isinstance(complete_event, TaskArtifactUpdateEvent)
            assert complete_event.artifact.name == "node_complete_process"

        finally:
            await redis_client.close()

    @pytest.mark.asyncio
    async def test_multi_node_flow_emits_all_events(self, container):
        """Агент с несколькими нодами эмитит события для каждой."""
        redis_client = container.redis_client
        await redis_client.connect()

        task_id = f"test-multi-node-{uuid.uuid4()}"
        context_id = f"ctx-{uuid.uuid4()}"

        # Агент с тремя function нодами
        agent = await Flow.from_config({
            "id": "test_multi_node_agent",
            "name": "Test Multi Node",
            "entry": "step1",
            "nodes": {
                "step1": {
                    "type": "code",
                    "code": "async def run(state):\n    state['step1'] = True\n    return state",
                },
                "step2": {
                    "type": "code",
                    "code": "async def run(state):\n    state['step2'] = True\n    return state",
                },
                "step3": {
                    "type": "code",
                    "code": "async def run(state):\n    state['response'] = 'all done'\n    return state",
                },
            },
            "edges": [
                {"from": "step1", "to": "step2"},
                {"from": "step2", "to": "step3"},
                {"from": "step3", "to": None},
            ],
        })

        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=f"test-agent:{context_id}",
            content="test",
        )

        subscriber = EventSubscriber(redis_client)
        ready_event = asyncio.Event()
        collected_events = []

        def _has_step3_complete() -> bool:
            for e in collected_events:
                if isinstance(e, TaskArtifactUpdateEvent) and e.artifact.name == "node_complete_step3":
                    return True
            return False

        async def collect():
            async for event in subscriber.subscribe(task_id, timeout=5.0, ready_event=ready_event):
                collected_events.append(event)
                if _has_step3_complete():
                    break

        async def execute():
            await ready_event.wait()
            await asyncio.sleep(0.05)
            await agent.run(state)

        try:
            await asyncio.wait_for(
                asyncio.gather(collect(), execute()),
                timeout=10.0
            )

            assert len(collected_events) >= 6

            # Проверяем последовательность
            node_names = []
            for event in collected_events:
                if isinstance(event, TaskArtifactUpdateEvent):
                    node_names.append(event.artifact.name)

            # Должны быть: start_step1, complete_step1, start_step2, complete_step2, start_step3, complete_step3
            assert "node_start_step1" in node_names
            assert "node_complete_step1" in node_names
            assert "node_start_step2" in node_names
            assert "node_complete_step2" in node_names
            assert "node_start_step3" in node_names
            assert "node_complete_step3" in node_names

            # Порядок: start перед complete для каждой ноды
            assert node_names.index("node_start_step1") < node_names.index("node_complete_step1")
            assert node_names.index("node_start_step2") < node_names.index("node_complete_step2")
            assert node_names.index("node_start_step3") < node_names.index("node_complete_step3")

        finally:
            await redis_client.close()

    @pytest.mark.asyncio
    async def test_node_error_emits_error_event(self, container):
        """При ошибке в ноде эмитится node_error."""
        redis_client = container.redis_client
        await redis_client.connect()

        task_id = f"test-node-error-{uuid.uuid4()}"
        context_id = f"ctx-{uuid.uuid4()}"

        # Агент с нодой которая падает
        agent = await Flow.from_config({
            "id": "test_error_node_agent",
            "name": "Test Error Node",
            "entry": "failing",
            "nodes": {
                "failing": {
                    "type": "code",
                    "code": "async def run(state):\n    raise ValueError('Test error')",
                },
            },
            "edges": [{"from": "failing", "to": None}],
        })

        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=f"test-agent:{context_id}",
            content="test",
        )

        subscriber = EventSubscriber(redis_client)
        ready_event = asyncio.Event()
        collected_events = []

        async def collect():
            async for event in subscriber.subscribe(task_id, timeout=5.0, ready_event=ready_event):
                collected_events.append(event)
                if len(collected_events) >= 2:
                    break

        async def execute():
            await ready_event.wait()
            await asyncio.sleep(0.05)
            try:
                await agent.run(state)
            except ValueError:
                pass  # Ожидаемая ошибка

        try:
            await asyncio.wait_for(
                asyncio.gather(collect(), execute()),
                timeout=10.0
            )

            assert len(collected_events) >= 2

            # Первое - node_start
            start_event = collected_events[0]
            assert isinstance(start_event, TaskArtifactUpdateEvent)
            assert start_event.artifact.name == "node_start_failing"

            # Второе - node_error
            error_event = collected_events[1]
            assert isinstance(error_event, TaskArtifactUpdateEvent)
            assert error_event.artifact.name == "node_error_failing"

        finally:
            await redis_client.close()

