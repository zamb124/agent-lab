"""
Интеграционные тесты TaskIQ.

Проверяют что:
1. API реально кикает задачи в Redis через TaskIQ
2. Tools выполняются через TaskIQ параллельно
3. Interrupt/resume работает через TaskIQ
4. Нет InMemory/моков Redis - всё реально

ВАЖНО: Используется реальный Redis (docker-compose-test.yaml).
Фикстура taskiq_worker запускает worker для обработки задач.
API возвращает A2A Task формат.

Маркер real_taskiq отключает sync_tools fixture.
"""

import uuid

import pytest

from apps.flows.src.tasks.flow_tasks import process_flow_task
from apps.flows.src.tasks.tool_tasks import execute_tool
from core.clients.llm import LLMToolCall
from core.state import ExecutionState, InterruptData

pytestmark = pytest.mark.real_taskiq


@pytest.fixture(autouse=True)
def require_taskiq_worker(taskiq_worker, container):
    """Все тесты в этом модуле требуют реальный TaskIQ worker."""
    container.use_worker = True
    yield
    container.use_worker = False


@pytest.mark.real_taskiq
class TestTaskIQToolExecution:
    """Тесты выполнения tools через TaskIQ."""

    @pytest.fixture
    def calculator_tool_config(self):
        """Inline конфиг calculator tool."""
        return {
            "tool_id": "taskiq_test_calculator",
            "title": "TaskIQ Test Calculator",
            "description": "Calculator for TaskIQ tests",
            "code": "\nasync def run(args, state):\n    a = args.get('a', 0)\n    b = args.get('b', 0)\n    op = args.get('op', 'add')\n    if op == 'add':\n        return a + b\n    elif op == 'mul':\n        return a * b\n    return 0\n",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                    "op": {"type": "string"},
                },
                "required": ["a", "b"],
            },
        }

    @pytest.mark.asyncio
    async def test_tool_executes_via_taskiq_kiq(
        self, app, container, calculator_tool_config, mock_context
    ):
        """Tool выполняется через TaskIQ .kiq() + wait_result()."""
        import asyncio

        from taskiq.exceptions import TaskiqResultTimeoutError

        await asyncio.sleep(0.15)
        state_dict = {
            "task_id": "test-task",
            "context_id": "test-context",
            "user_id": "test-user",
            "session_id": "test:test-context",
        }
        task = await execute_tool.kiq(
            calculator_tool_config,
            {"a": 10, "b": 5, "op": "add"},
            state_dict,
            context_data=mock_context.to_dict(),
        )
        try:
            result = await task.wait_result(timeout=5)
        except TaskiqResultTimeoutError as exc:
            raise AssertionError(
                "TaskIQ worker не обработал задачу за 5 секунд (проверьте, что воркер запущен и Redis доступен)"
            ) from exc
        assert not result.is_err, f"Task failed: {result.error}"
        assert result.return_value["tool_id"] == "taskiq_test_calculator"
        assert result.return_value["result"] == 15

    @pytest.mark.asyncio
    async def test_multiple_tools_execute_parallel_via_taskiq(
        self, app, container, calculator_tool_config, mock_context
    ):
        """Несколько tools кикаются параллельно и ждём все результаты."""
        state_dict = {
            "task_id": "test-task",
            "context_id": "test-context",
            "user_id": "test-user",
            "session_id": "test:test-context",
        }
        tasks = []
        for i in range(5):
            task = await execute_tool.kiq(
                calculator_tool_config,
                {"a": i, "b": i * 2, "op": "mul"},
                state_dict,
                context_data=mock_context.to_dict(),
            )
            tasks.append((i, task))
        results = []
        for i, task in tasks:
            result = await task.wait_result(timeout=5)
            assert not result.is_err, f"Task {i} failed: {result.error}"
            results.append(result.return_value["result"])
        expected = [0, 2, 8, 18, 32]
        assert results == expected

    @pytest.mark.asyncio
    async def test_tool_receives_state(self, app, container, mock_context):
        """Tool получает state и может его использовать."""
        tool_config = {
            "tool_id": "taskiq_state_tool",
            "title": "State Tool",
            "description": "Tool that uses state",
            "code": "\nasync def run(args, state):\n    prefix = state.get('prefix', '')\n    value = args.get('value', '')\n    return f\"{prefix}:{value}\"\n",
            "parameters_schema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        }
        state_dict = {
            "task_id": "test-task",
            "context_id": "test-context",
            "user_id": "test-user",
            "session_id": "test:test-context",
            "prefix": "STATE",
        }
        task = await execute_tool.kiq(
            tool_config, {"value": "test"}, state_dict, context_data=mock_context.to_dict()
        )
        result = await task.wait_result(timeout=5)
        assert not result.is_err
        assert result.return_value["tool_id"] == "taskiq_state_tool"
        assert result.return_value["result"] == "STATE:test"

    @pytest.mark.asyncio
    async def test_tools_results_merged_to_state(
        self, app, container, calculator_tool_config, unique_id
    ):
        """Результаты tools мержатся в state.tool_results."""
        from apps.flows.src.models import NodeConfig
        from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner

        tool2_id = f"taskiq_multiplier_{unique_id}"
        tool2_config = {
            "tool_id": tool2_id,
            "title": "Multiplier",
            "description": "Multiplies",
            "code": "\nasync def run(args, state):\n    return args.get('x', 0) * 2\n",
            "parameters_schema": {
                "type": "object",
                "properties": {"x": {"type": "number"}},
                "required": ["x"],
            },
        }
        tool1 = await container.tool_registry.create_tool(calculator_tool_config)
        tool2 = await container.tool_registry.create_tool(tool2_config)
        node_config = NodeConfig(
            node_id="test_node", name="Test Node", type="llm_node", prompt="Test"
        )
        runner = LlmNodeRunner(
            node_config=node_config,
            tools=[tool1, tool2],
            llm=None,
            prompt="Test",
            container=container,
        )
        tool_calls = [
            LLMToolCall(
                name="taskiq_test_calculator",
                arguments={"a": 5, "b": 3, "op": "add"},
                id="call_1",
            ),
            LLMToolCall(name=tool2_id, arguments={"x": 10}, id="call_2"),
        ]
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test",
        )
        await runner._execute_tools_parallel(tool_calls, state)
        assert state.tool_results
        assert "taskiq_test_calculator" in state.tool_results
        assert tool2_id in state.tool_results
        assert state.tool_results["taskiq_test_calculator"] == 8
        assert state.tool_results[tool2_id] == 20


class TestTaskIQFlowExecution:
    """Тесты выполнения flow через TaskIQ."""

    @pytest.fixture
    async def setup_simple_flow(self, app, container, unique_id):
        """Создает простой flow для тестов."""
        from apps.flows.src.models import FlowConfig

        flow_id = f"taskiq_simple_flow_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="TaskIQ Simple Agent",
            entry="init",
            nodes={
                "init": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['step'] = 'init'\n    return state",
                },
                "process": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['step'] = 'process'\n    state['response'] = 'Done'\n    return state",
                },
            },
            edges=[
                {"from_node": "init", "to_node": "process"},
                {"from_node": "process", "to_node": None},
            ],
        )
        await container.flow_repository.set(flow_config)
        return flow_id

    @pytest.mark.asyncio
    async def test_flow_executes_via_taskiq_kiq(
        self, app, container, setup_simple_flow, unique_id, mock_context
    ):
        """Agent выполняется через TaskIQ .kiq() + wait_result()."""
        flow_id = setup_simple_flow
        session_id = f"{flow_id}:taskiq-session-{unique_id}-{uuid.uuid4().hex[:8]}"
        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"
        task = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Test",
            context_data=mock_context.model_dump(),
        )
        result = await task.wait_result(timeout=5)
        assert not result.is_err, f"Task failed: {result.error}"
        assert result.return_value["task_state"] == "completed"
        assert result.return_value["response"] == "Done"


class TestTaskIQInterruptResume:
    """Тесты interrupt/resume через TaskIQ."""

    @pytest.fixture
    async def setup_interrupt_flow(self, app, container, unique_id):
        """Создает flow с interrupt для тестов."""
        from apps.flows.src.models import FlowConfig

        flow_id = f"taskiq_interrupt_flow_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="TaskIQ Interrupt Agent",
            entry="ask",
            nodes={
                "ask": {
                    "type": "code",
                    "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    if 'name' in state:\n        return state\n    if state.get('asked_name'):\n        state['name'] = state.get('content', '')\n        return state\n    state['asked_name'] = True\n    raise FlowInterrupt(question='What is your name?')\n",
                },
                "greet": {
                    "type": "code",
                    "code": "\nasync def run(args, state):\n    name = state.get('name', 'Unknown')\n    state['response'] = f'Hello, {name}!'\n    return state\n",
                },
            },
            edges=[
                {"from_node": "ask", "to_node": "greet"},
                {"from_node": "greet", "to_node": None},
            ],
        )
        await container.flow_repository.set(flow_config)
        return flow_id

    @pytest.mark.asyncio
    async def test_interrupt_via_taskiq(
        self, app, container, setup_interrupt_flow, unique_id, mock_context
    ):
        """Interrupt работает через TaskIQ."""
        flow_id = setup_interrupt_flow
        session_id = f"{flow_id}:taskiq-interrupt-{unique_id}-{uuid.uuid4().hex[:8]}"
        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"
        task = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Start",
            context_data=mock_context.model_dump(),
        )
        result = await task.wait_result(timeout=5)
        assert not result.is_err, f"Task failed: {result.error}"
        assert result.return_value["task_state"] == "input-required"
        interrupt = InterruptData.model_validate(result.return_value["interrupt"])
        assert interrupt.question == "What is your name?"

    @pytest.mark.asyncio
    async def test_resume_via_taskiq(
        self, app, container, setup_interrupt_flow, unique_id, mock_context
    ):
        """Resume после interrupt работает через TaskIQ."""
        flow_id = setup_interrupt_flow
        session_id = f"{flow_id}:taskiq-resume-{unique_id}-{uuid.uuid4().hex[:8]}"
        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"
        task1 = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Start",
            context_data=mock_context.model_dump(),
        )
        result1 = await task1.wait_result(timeout=5)
        if result1.is_err:
            print("\n❌ Task1 failed!")
            print(f"Error: {result1.error}")
        assert not result1.is_err, f"Task1 failed: {result1.error}"
        assert result1.return_value["task_state"] == "input-required"
        task2 = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Alice",
            is_resume=True,
            context_data=mock_context.model_dump(),
        )
        result2 = await task2.wait_result(timeout=5)
        assert not result2.is_err, f"Resume failed: {result2.error}"
        assert result2.return_value["task_state"] == "completed"
        assert "Alice" in result2.return_value["response"]


class TestTaskIQAPIIntegration:
    """Тесты интеграции API с TaskIQ."""

    @pytest.fixture
    async def setup_api_flow(self, app, container, unique_id):
        """Создает flow для тестов API."""
        from apps.flows.src.models import FlowConfig

        flow_id = f"taskiq_api_flow_{unique_id}_{uuid.uuid4().hex[:8]}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="TaskIQ API Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['response'] = f\"Got: {state.get('content', '')}\"\n    return state",
                }
            },
            edges=[{"from_node": "main", "to_node": None}],
        )
        await container.flow_repository.set(flow_config)
        return flow_id

    @pytest.mark.asyncio
    async def test_api_submit_uses_taskiq(self, client, setup_api_flow, unique_id):
        """API /tasks/submit использует TaskIQ внутри."""
        flow_id = setup_api_flow
        session_id = f"{flow_id}:api-taskiq-{unique_id}-{uuid.uuid4().hex[:8]}"
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={"flow_id": flow_id, "content": "Hello TaskIQ", "session_id": session_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"]["state"] == "completed"
        response_text = data["status"]["message"]["parts"][0]["text"]
        assert "Hello TaskIQ" in response_text

    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_a2a_endpoint_uses_taskiq(self, client, setup_api_flow, unique_id):
        """A2A endpoint использует TaskIQ внутри."""
        flow_id = setup_api_flow
        task_id = str(uuid.uuid4())
        context_id = f"a2a-taskiq-{unique_id}-{uuid.uuid4().hex[:8]}"
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Hello A2A TaskIQ"}],
                        "contextId": context_id,
                        "taskId": task_id,
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert data["result"]["status"]["state"] == "completed"
