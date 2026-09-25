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
from core.a2a import get_part_data
from core.errors import CodeExecutionRuntimeError
from core.flow_ui.templates import default_chat_document
from core.state import ExecutionState
from tests.flows.durable_runtime_harness import run_flow


@pytest.mark.real_taskiq
class TestNodeEventsStreaming:
    """Интеграционные тесты стриминга событий нод."""

    @pytest.mark.asyncio
    async def test_function_node_emits_start_and_complete(self, di):
        """Function нода эмитит node_start и node_complete."""
        redis_client = di.redis_client
        await redis_client.connect()
        task_id = f"test-node-events-{uuid.uuid4()}"
        context_id = f"ctx-{uuid.uuid4()}"
        flow_id = "test_node_events_agent"
        agent = await Flow.from_config(
            {
                "flow_id": flow_id,
                "name": "Test Node Events",
                "interface": default_chat_document().model_dump(mode="json"),
                "entry": "process",
                "nodes": {
                    "process": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['response'] = 'done'\n    return state",
                    }
                },
                "edges": [{"from_node": "process", "to_node": None}],
            },
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )
        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=f"{flow_id}:{context_id}",
            content="test input",
        )
        subscriber = EventSubscriber(redis_client)
        ready_event = asyncio.Event()
        collected_events = []

        async def collect():
            async for event in subscriber.subscribe(task_id, timeout=5.0, ready_event=ready_event):
                collected_events.append(event)
                if len(collected_events) >= 2:
                    break

        async def execute(di):
            await ready_event.wait()
            await asyncio.sleep(0.05)
            await run_flow(di=di, flow=agent, state=state)

        try:
            await asyncio.wait_for(asyncio.gather(collect(), execute(di)), timeout=10.0)
            assert len(collected_events) >= 2
            start_event = collected_events[0]
            assert isinstance(start_event, TaskArtifactUpdateEvent)
            assert start_event.artifact.name == "node_start_process"
            complete_event = collected_events[1]
            assert isinstance(complete_event, TaskArtifactUpdateEvent)
            assert complete_event.artifact.name == "node_complete_process"
            complete_data = get_part_data(complete_event.artifact.parts[0])
            assert complete_data["event"] == "node_complete"
            assert complete_data["node_id"] == "process"
            assert complete_data["node_type"] == "code"
            assert isinstance(complete_data["duration_ms"], (int, float))
            assert complete_data["run_index"] == 0
            assert isinstance(complete_data["result_preview"], str)
            assert isinstance(complete_data["diff"], list)
        finally:
            await redis_client.close()

    @pytest.mark.asyncio
    async def test_multi_node_flow_emits_all_events(self, di):
        """Агент с несколькими нодами эмитит события для каждой."""
        redis_client = di.redis_client
        await redis_client.connect()
        task_id = f"test-multi-node-{uuid.uuid4()}"
        context_id = f"ctx-{uuid.uuid4()}"
        flow_id = "test_multi_node_agent"
        agent = await Flow.from_config(
            {
                "flow_id": flow_id,
                "name": "Test Multi Node",
                "interface": default_chat_document().model_dump(mode="json"),
                "entry": "step1",
                "nodes": {
                    "step1": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['step1'] = True\n    return state",
                    },
                    "step2": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['step2'] = True\n    return state",
                    },
                    "step3": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['response'] = 'all done'\n    return state",
                    },
                },
                "edges": [
                    {"from_node": "step1", "to_node": "step2"},
                    {"from_node": "step2", "to_node": "step3"},
                    {"from_node": "step3", "to_node": None},
                ],
            },
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )
        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=f"{flow_id}:{context_id}",
            content="test",
        )
        subscriber = EventSubscriber(redis_client)
        ready_event = asyncio.Event()
        collected_events = []

        def _has_step3_complete() -> bool:
            for e in collected_events:
                if (
                    isinstance(e, TaskArtifactUpdateEvent)
                    and e.artifact.name == "node_complete_step3"
                ):
                    return True
            return False

        async def collect():
            async for event in subscriber.subscribe(task_id, timeout=5.0, ready_event=ready_event):
                collected_events.append(event)
                if _has_step3_complete():
                    break

        async def execute(di):
            await ready_event.wait()
            await asyncio.sleep(0.05)
            await run_flow(di=di, flow=agent, state=state)

        try:
            await asyncio.wait_for(asyncio.gather(collect(), execute(di)), timeout=10.0)
            assert len(collected_events) >= 6
            node_names = []
            for event in collected_events:
                if isinstance(event, TaskArtifactUpdateEvent):
                    node_names.append(event.artifact.name)
            assert "node_start_step1" in node_names
            assert "node_complete_step1" in node_names
            assert "node_start_step2" in node_names
            assert "node_complete_step2" in node_names
            assert "node_start_step3" in node_names
            assert "node_complete_step3" in node_names
            assert node_names.index("node_start_step1") < node_names.index("node_complete_step1")
            assert node_names.index("node_start_step2") < node_names.index("node_complete_step2")
            assert node_names.index("node_start_step3") < node_names.index("node_complete_step3")
        finally:
            await redis_client.close()

    @pytest.mark.asyncio
    async def test_node_complete_emits_full_diff_over_eight_items(
        self,
        di,
        unique_id,
    ):
        """node_complete.diff содержит все изменения ноды, включая длинное значение."""
        redis_client = di.redis_client
        await redis_client.connect()
        task_id = f"test-node-diff-{unique_id}"
        context_id = f"ctx-{unique_id}"
        flow_id = f"test_node_diff_{unique_id}"
        long_text = "X" * 400
        field_assigns = "\n".join(
            f"    state['field_{index}'] = {index}" for index in range(9)
        )
        agent = await Flow.from_config(
            {
                "flow_id": flow_id,
                "name": "Test Full Diff",
                "interface": default_chat_document().model_dump(mode="json"),
                "entry": "write_many",
                "nodes": {
                    "write_many": {
                        "type": "code",
                        "code": (
                            "async def run(args, state):\n"
                            "    state['response'] = 'ok'\n"
                            f"    state['big'] = '{'X' * 400}'\n"
                            f"{field_assigns}\n"
                            "    return state"
                        ),
                    }
                },
                "edges": [{"from_node": "write_many", "to_node": None}],
            },
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )
        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id=f"user-{unique_id}",
            session_id=f"{flow_id}:{context_id}",
            content="test input",
        )
        subscriber = EventSubscriber(redis_client)
        ready_event = asyncio.Event()
        collected_events = []

        async def collect():
            async for event in subscriber.subscribe(task_id, timeout=5.0, ready_event=ready_event):
                collected_events.append(event)
                if (
                    isinstance(event, TaskArtifactUpdateEvent)
                    and event.artifact.name == "node_complete_write_many"
                ):
                    break

        async def execute(di):
            await ready_event.wait()
            await asyncio.sleep(0.05)
            await run_flow(di=di, flow=agent, state=state)

        try:
            await asyncio.wait_for(asyncio.gather(collect(), execute(di)), timeout=10.0)
            complete_event = None
            for event in collected_events:
                if (
                    isinstance(event, TaskArtifactUpdateEvent)
                    and event.artifact.name == "node_complete_write_many"
                ):
                    complete_event = event
                    break
            assert complete_event is not None
            complete_data = get_part_data(complete_event.artifact.parts[0])
            assert complete_data["event"] == "node_complete"
            assert complete_data["node_id"] == "write_many"
            diff_items = complete_data["diff"]
            assert isinstance(diff_items, list)
            assert len(diff_items) > 8
            by_path = {item["path"]: item for item in diff_items}
            assert by_path["response"]["new_value"] == "ok"
            assert by_path["big"]["new_value"] == long_text
            for index in range(9):
                assert by_path[f"field_{index}"]["new_value"] == index
                assert by_path[f"field_{index}"]["change_type"] == "added"
        finally:
            await redis_client.close()

    @pytest.mark.asyncio
    async def test_node_error_emits_error_event(self, di):
        """При ошибке в ноде эмитится node_error."""
        redis_client = di.redis_client
        await redis_client.connect()
        task_id = f"test-node-error-{uuid.uuid4()}"
        context_id = f"ctx-{uuid.uuid4()}"
        flow_id = "test_error_node_agent"
        agent = await Flow.from_config(
            {
                "flow_id": flow_id,
                "name": "Test Error Node",
                "interface": default_chat_document().model_dump(mode="json"),
                "entry": "failing",
                "nodes": {
                    "failing": {
                        "type": "code",
                        "code": "async def run(args, state):\n    raise ValueError('Test error')",
                    }
                },
                "edges": [{"from_node": "failing", "to_node": None}],
            },
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )
        state = ExecutionState.create(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=f"{flow_id}:{context_id}",
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

        async def execute(di):
            await ready_event.wait()
            await asyncio.sleep(0.05)
            try:
                await run_flow(di=di, flow=agent, state=state)
            except (ValueError, CodeExecutionRuntimeError):
                pass

        try:
            await asyncio.wait_for(asyncio.gather(collect(), execute(di)), timeout=10.0)
            assert len(collected_events) >= 2
            start_event = collected_events[0]
            assert isinstance(start_event, TaskArtifactUpdateEvent)
            assert start_event.artifact.name == "node_start_failing"
            error_event = collected_events[1]
            assert isinstance(error_event, TaskArtifactUpdateEvent)
            assert error_event.artifact.name == "node_error_failing"
        finally:
            await redis_client.close()
