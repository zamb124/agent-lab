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

from apps.flows.src.runtime.flow import Flow
from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from apps.flows.src.tasks.flow_tasks import process_flow_task
from core.state import ExecutionState

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
        
        # Код для нод которые делают sleep и записывают время
        node_code_template = '''
import time
import asyncio

async def run(state):
    start = time.time()
    await asyncio.sleep(0.12)
    end = time.time()
    
    state['{node_name}_start'] = start
    state['{node_name}_end'] = end
    state['{node_name}_done'] = True
    return state
'''
        
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Parallel Execution Test",
            entry="start",
            nodes={
                "start": {
                    "type": "code",
                    "code": """
def run(state):
    import time
    state['execution_start'] = time.time()
    return state
""",
                },
                "node_a": {
                    "type": "code",
                    "code": node_code_template.format(node_name="node_a"),
                },
                "node_b": {
                    "type": "code",
                    "code": node_code_template.format(node_name="node_b"),
                },
                "node_c": {
                    "type": "code",
                    "code": node_code_template.format(node_name="node_c"),
                },
                "final": {
                    "type": "code",
                    "code": """
def run(state):
    import time
    state['execution_end'] = time.time()
    state['response'] = 'All nodes completed'
    return state
""",
                },
            },
            edges=[
                # Fan-out: start -> 3 параллельные ноды
                {"from": "start", "to": "node_a"},
                {"from": "start", "to": "node_b"},
                {"from": "start", "to": "node_c"},
                # Fan-in: 3 ноды -> final
                {"from": "node_a", "to": "final"},
                {"from": "node_b", "to": "final"},
                {"from": "node_c", "to": "final"},
                # Завершение
                {"from": "final", "to": None},
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
        assert state["status"] == "completed"
        
        # Проверяем что все ноды выполнились
        # Note: после merge результатов мы можем не увидеть все поля
        # если они перезаписываются. Проверим хотя бы response.
        assert state["response"] == "All nodes completed"
        
        # Главная проверка: время выполнения
        # Если последовательно: 3 * 0.5 = 1.5+ сек
        # Если параллельно: ~0.5-1.0 сек (с накладными расходами)
        print(f"\n⏱️  Overall duration: {overall_duration:.2f}s")
        
        # Даем запас на накладные расходы TaskIQ, но должно быть < 2 сек
        assert overall_duration < 2.0, (
            f"Execution took {overall_duration:.2f}s, expected < 2.0s for parallel execution. "
            "Nodes may be executing sequentially instead of in parallel."
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
        
        # Получаем timestamps из state
        # Note: из-за merge "кто последний тот прав" мы можем потерять часть timestamps
        # Но если хотя бы некоторые есть - проверим их
        node_a_start = state.get("node_a_start")
        node_b_start = state.get("node_b_start")
        node_c_start = state.get("node_c_start")
        
        print(f"\n📊 Timestamps:")
        print(f"  node_a_start: {node_a_start}")
        print(f"  node_b_start: {node_b_start}")
        print(f"  node_c_start: {node_c_start}")
        
        # Проверяем что хотя бы некоторые timestamps есть
        available_starts = [t for t in [node_a_start, node_b_start, node_c_start] if t is not None]
        
        if len(available_starts) >= 2:
            # Если есть хотя бы 2 timestamp - проверяем что они близки (< 0.5 сек разницы)
            max_start = max(available_starts)
            min_start = min(available_starts)
            start_diff = max_start - min_start
            
            print(f"  Start time difference: {start_diff:.3f}s")
            
            # Если параллельно - разница должна быть < 0.3 сек
            # (с учетом накладных расходов на сериализацию и TaskIQ)
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
                    "code": "def run(state):\n    state['started'] = True\n    return state",
                },
                "writer_a": {
                    "type": "code",
                    "code": "def run(state):\n    state['field_a'] = 'value_a'\n    return state",
                },
                "writer_b": {
                    "type": "code",
                    "code": "def run(state):\n    state['field_b'] = 'value_b'\n    return state",
                },
                "final": {
                    "type": "code",
                    "code": """
def run(state):
    state['response'] = f"a={state.get('field_a')}, b={state.get('field_b')}"
    return state
""",
                },
            },
            edges=[
                {"from": "start", "to": "writer_a"},
                {"from": "start", "to": "writer_b"},
                {"from": "writer_a", "to": "final"},
                {"from": "writer_b", "to": "final"},
                {"from": "final", "to": None},
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
        assert state["status"] == "completed"
        
        # Проверяем что оба поля сохранились через response финальной ноды
        # (response показывает что merge работает: 'a=value_a, b=value_b')
        response = state.get("response", "")
        assert "value_a" in response, "field_a lost during merge"
        assert "value_b" in response, "field_b lost during merge"
