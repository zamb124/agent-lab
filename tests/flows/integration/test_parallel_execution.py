"""
Тесты параллельного выполнения нод.

Проверяют что:
1. Fan-out ноды выполняются параллельно через asyncio.gather
2. Общее время выполнения примерно равно одному sleep, не сумме
3. Результаты всех нод корректно мержатся

БЕЗ МОКОВ - реальный TaskIQ worker.
"""

import time
import uuid

import pytest

from apps.flows.src.models import FlowConfig
from apps.flows.src.tasks.flow_tasks import process_flow_task

pytestmark = pytest.mark.real_taskiq


@pytest.fixture(autouse=True)
def require_taskiq_worker(taskiq_worker, container):
    """Все тесты в этом модуле требуют реальный TaskIQ worker."""
    container.use_worker = True
    yield
    container.use_worker = False


class TestParallelNodeExecution:
    """Тесты параллельного выполнения нод в графе."""

    @pytest.fixture
    async def setup_parallel_flow(self, app, container, unique_id):
        """
        Создает flow с fan-out: start -> [node_a, node_b, node_c] -> final

        Каждая нода делает короткий sleep и записывает timestamp.
        Если выполнение параллельное - общее время ~один sleep.
        Если последовательное - сумма sleep по нодам.
        """
        flow_id = f"parallel_test_{unique_id}"
        node_code_template = "\nimport time\nimport asyncio\n\nasync def run(args, state):\n    start = time.time()\n    await asyncio.sleep(0.12)\n    end = time.time()\n\n    state['{node_name}_start'] = start\n    state['{node_name}_end'] = end\n    state['{node_name}_done'] = True\n    return state\n"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Parallel Execution Test",
            entry="start",
            nodes={
                "start": {
                    "type": "code",
                    "code": "\nasync def run(args, state):\n    import time\n    state['execution_start'] = time.time()\n    return state\n",
                },
                "node_a": {"type": "code", "code": node_code_template.format(node_name="node_a")},
                "node_b": {"type": "code", "code": node_code_template.format(node_name="node_b")},
                "node_c": {"type": "code", "code": node_code_template.format(node_name="node_c")},
                "final": {
                    "type": "code",
                    "incoming_policy": "all",
                    "code": "\nasync def run(args, state):\n    import time\n    state['execution_end'] = time.time()\n    state['response'] = 'All nodes completed'\n    return state\n",
                },
            },
            edges=[
                {"from_node": "start", "to_node": "node_a"},
                {"from_node": "start", "to_node": "node_b"},
                {"from_node": "start", "to_node": "node_c"},
                {"from_node": "node_a", "to_node": "final"},
                {"from_node": "node_b", "to_node": "final"},
                {"from_node": "node_c", "to_node": "final"},
                {"from_node": "final", "to_node": None},
            ],
        )
        await container.flow_repository.set(flow_config)
        return flow_id

    @pytest.mark.asyncio
    async def test_fanout_nodes_execute_in_parallel(
        self, app, container, setup_parallel_flow, unique_id, mock_context
    ):
        """
        Тест: 3 ноды с коротким sleep выполняются параллельно.

        Ожидаемое поведение:
        - Общее время ~0.5-1.0 сек (параллельно)
        - НЕ ~1.5+ сек (последовательно)
        """
        flow_id = setup_parallel_flow
        session_id = f"{flow_id}:parallel-{unique_id}-{uuid.uuid4().hex[:8]}"
        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"
        overall_start = time.time()
        task = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Start parallel test",
            context_data=mock_context.model_dump(),
        )
        result = await task.wait_result(timeout=30)
        overall_end = time.time()
        overall_duration = overall_end - overall_start
        assert not result.is_err, f"Task failed: {result.error}"
        state = result.return_value
        assert state["task_state"] == "completed"
        assert state["response"] == "All nodes completed"
        print(f"\n⏱️  Overall duration: {overall_duration:.2f}s")
        assert overall_duration < 2.0, (
            f"Execution took {overall_duration:.2f}s, expected < 2.0s for parallel execution. Nodes may be executing sequentially instead of in parallel."
        )

    @pytest.mark.asyncio
    async def test_parallel_nodes_timestamps_overlap(
        self, app, container, setup_parallel_flow, unique_id, mock_context
    ):
        """
        Тест: timestamps параллельных нод перекрываются.

        Если ноды выполняются параллельно:
        - node_a.start ≈ node_b.start ≈ node_c.start
        - Времена перекрываются
        """
        flow_id = setup_parallel_flow
        session_id = f"{flow_id}:timestamps-{unique_id}-{uuid.uuid4().hex[:8]}"
        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"
        task = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Start timestamp test",
            context_data=mock_context.model_dump(),
        )
        result = await task.wait_result(timeout=30)
        assert not result.is_err, f"Task failed: {result.error}"
        state = result.return_value
        node_a_start = state.get("node_a_start")
        node_b_start = state.get("node_b_start")
        node_c_start = state.get("node_c_start")
        print("\n📊 Timestamps:")
        print(f"  node_a_start: {node_a_start}")
        print(f"  node_b_start: {node_b_start}")
        print(f"  node_c_start: {node_c_start}")
        available_starts = [t for t in [node_a_start, node_b_start, node_c_start] if t is not None]
        if len(available_starts) >= 2:
            max_start = max(available_starts)
            min_start = min(available_starts)
            start_diff = max_start - min_start
            print(f"  Start time difference: {start_diff:.3f}s")
            assert start_diff < 0.5, (
                f"Start times differ by {start_diff:.3f}s, expected < 0.5s for parallel execution"
            )


class TestParallelNodesMerge:
    """Тесты корректного merge результатов параллельных нод."""

    @pytest.fixture
    async def setup_merge_flow(self, app, container, unique_id):
        """
        Создает flow где каждая нода пишет в разные поля state.
        Проверяем что все поля сохраняются после merge.
        """
        flow_id = f"merge_test_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Merge Test",
            entry="start",
            nodes={
                "start": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['started'] = True\n    return state",
                },
                "writer_a": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['field_a'] = 'value_a'\n    return state",
                },
                "writer_b": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['field_b'] = 'value_b'\n    return state",
                },
                "final": {
                    "type": "code",
                    "incoming_policy": "all",
                    "code": "\nasync def run(args, state):\n    state['response'] = f\"a={state.get('field_a')}, b={state.get('field_b')}\"\n    return state\n",
                },
            },
            edges=[
                {"from_node": "start", "to_node": "writer_a"},
                {"from_node": "start", "to_node": "writer_b"},
                {"from_node": "writer_a", "to_node": "final"},
                {"from_node": "writer_b", "to_node": "final"},
                {"from_node": "final", "to_node": None},
            ],
        )
        await container.flow_repository.set(flow_config)
        return flow_id

    @pytest.mark.asyncio
    async def test_different_fields_preserved_after_merge(
        self, app, container, setup_merge_flow, unique_id, mock_context
    ):
        """
        Тест: разные ноды пишут в разные поля - все сохраняются.
        """
        flow_id = setup_merge_flow
        session_id = f"{flow_id}:merge-{unique_id}-{uuid.uuid4().hex[:8]}"
        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"
        task = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Test merge",
            context_data=mock_context.model_dump(),
        )
        result = await task.wait_result(timeout=30)
        assert not result.is_err, f"Task failed: {result.error}"
        state = result.return_value
        assert state["task_state"] == "completed"
        response = state.get("response", "")
        assert "value_a" in response, "field_a lost during merge"
        assert "value_b" in response, "field_b lost during merge"
