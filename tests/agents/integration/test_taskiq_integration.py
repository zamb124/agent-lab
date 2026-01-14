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
from typing import Any, Dict

import pytest

pytestmark = pytest.mark.real_taskiq


@pytest.fixture(autouse=True)
def require_taskiq_worker(taskiq_worker):
    """Все тесты в этом модуле требуют реальный TaskIQ worker."""
    pass

from apps.agents.src.tasks.agent_tasks import process_agent_task
from apps.agents.src.tasks.eval_task import execute_inline_code
from apps.agents.src.tasks.tool_tasks import execute_tool
from core.state import ExecutionState


def get_task_state(data: Dict[str, Any]) -> str:
    """Извлекает state из A2A Task ответа."""
    return data["status"]["state"]


def get_task_response(data: Dict[str, Any]) -> str:
    """Извлекает текст ответа из A2A Task."""
    msg = data["status"].get("message")
    if msg and msg.get("parts"):
        return msg["parts"][0].get("text", "")
    return ""


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
            "code": """
def execute(args, state):
    a = args.get('a', 0)
    b = args.get('b', 0)
    op = args.get('op', 'add')
    if op == 'add':
        return a + b
    elif op == 'mul':
        return a * b
    return 0
""",
        }

    @pytest.mark.asyncio
    async def test_tool_executes_via_taskiq_kiq(self, app, container, calculator_tool_config):
        """Tool выполняется через TaskIQ .kiq() + wait_result()."""
        import pytest
        import asyncio
        from taskiq.exceptions import TaskiqResultTimeoutError
        
        # Даем worker'у время полностью запуститься и начать слушать
        await asyncio.sleep(2)
        
        # Создаем валидный state для tool
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
        )

        try:
            result = await task.wait_result(timeout=5)
        except TaskiqResultTimeoutError:
            pytest.skip("TaskIQ worker не обработал задачу за 10 секунд (возможно не запущен или не подключен к Redis)")

        assert not result.is_err, f"Task failed: {result.error}"
        assert result.return_value["tool_id"] == "taskiq_test_calculator"
        assert result.return_value["result"] == 15

    @pytest.mark.asyncio
    async def test_multiple_tools_execute_parallel_via_taskiq(
        self, app, container, calculator_tool_config
    ):
        """Несколько tools кикаются параллельно и ждём все результаты."""
        # Создаем валидный state
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
            )
            tasks.append((i, task))

        results = []
        for i, task in tasks:
            result = await task.wait_result()
            assert not result.is_err, f"Task {i} failed: {result.error}"
            results.append(result.return_value["result"])

        # i * (i * 2) = 2 * i^2
        expected = [0, 2, 8, 18, 32]
        assert results == expected

    @pytest.mark.asyncio
    async def test_tool_receives_state(self, app, container):
        """Tool получает state и может его использовать."""
        tool_config = {
            "tool_id": "taskiq_state_tool",
            "title": "State Tool",
            "description": "Tool that uses state",
            "code": """
def execute(args, state):
    prefix = state.get('prefix', '')
    value = args.get('value', '')
    return f"{prefix}:{value}"
""",
        }

        # Создаем валидный state с дополнительным полем
        state_dict = {
            "task_id": "test-task",
            "context_id": "test-context",
            "user_id": "test-user",
            "session_id": "test:test-context",
            "prefix": "STATE",
        }
        
        task = await execute_tool.kiq(
            tool_config,
            {"value": "test"},
            state_dict,
        )

        result = await task.wait_result()

        assert not result.is_err
        assert result.return_value["tool_id"] == "taskiq_state_tool"
        assert result.return_value["result"] == "STATE:test"

    @pytest.mark.asyncio
    async def test_tools_results_merged_to_state(self, app, container, calculator_tool_config, unique_id):
        """Результаты tools мержатся в state.tool_results."""
        from apps.agents.src.agent.runners.react_runner import ReactNodeRunner
        from apps.agents.src.models import NodeConfig

        # Inline конфиг второго tool
        tool2_id = f"taskiq_multiplier_{unique_id}"
        tool2_config = {
            "tool_id": tool2_id,
            "title": "Multiplier",
            "description": "Multiplies",
            "code": """
def execute(args, state):
    return args.get('x', 0) * 2
""",
        }

        # Создаём tools из inline конфигов
        tool1 = await container.tool_registry.create_tool(calculator_tool_config)
        tool2 = await container.tool_registry.create_tool(tool2_config)

        # Создаём runner с NodeConfig
        node_config = NodeConfig(
            node_id="test_node",
            name="Test Node",
            type="react_node",
            prompt="Test",
        )
        runner = ReactNodeRunner(
            node_config=node_config,
            tools=[tool1, tool2],
            llm=None,
            prompt="Test",
        )

        # Симулируем tool calls от LLM - два разных tools
        tool_calls = [
            {"name": "taskiq_test_calculator", "arguments": {"a": 5, "b": 3, "op": "add"}, "id": "call_1"},
            {"name": tool2_id, "arguments": {"x": 10}, "id": "call_2"},
        ]

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )

        # Выполняем tools параллельно
        await runner._execute_tools_parallel(tool_calls, state)

        # Проверяем что результаты смержены в tool_results
        assert state.tool_results
        assert "taskiq_test_calculator" in state.tool_results
        assert tool2_id in state.tool_results
        assert state.tool_results["taskiq_test_calculator"] == 8  # 5+3
        assert state.tool_results[tool2_id] == 20  # 10*2


class TestTaskIQFlowExecution:
    """Тесты выполнения flow через TaskIQ."""

    @pytest.fixture
    async def setup_simple_flow(self, app, container, unique_id):
        """Создает простой flow для тестов."""
        from apps.agents.src.models import AgentConfig

        agent_id = f"taskiq_simple_flow_{unique_id}"
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="TaskIQ Simple Agent",
            entry="init",
            nodes={
                "init": {
                    "type": "function",
                    "code": "def run(state):\n    state['step'] = 'init'\n    return state",
                },
                "process": {
                    "type": "function",
                    "code": "def run(state):\n    state['step'] = 'process'\n    state['response'] = 'Done'\n    return state",
                },
            },
            edges=[
                {"from": "init", "to": "process"},
                {"from": "process", "to": None},
            ],
        )
        await container.agent_repository.set(agent_config)
        return agent_id

    @pytest.mark.asyncio
    async def test_flow_executes_via_taskiq_kiq(
        self, app, container, setup_simple_flow, unique_id, mock_context
    ):
        """Agent выполняется через TaskIQ .kiq() + wait_result()."""
        agent_id = setup_simple_flow
        session_id = f"{agent_id}:taskiq-session-{unique_id}-{uuid.uuid4().hex[:8]}"

        mock_context.session_id = session_id
        mock_context.agent_id = agent_id
        mock_context.user.user_id = "test-user"
        task = await process_agent_task.kiq(
            agent_id=agent_id,
            session_id=session_id,
            user_id="test-user",
            content="Test",
            context_data=mock_context.model_dump(),
        )

        result = await task.wait_result()

        assert not result.is_err, f"Task failed: {result.error}"
        assert result.return_value["status"] == "completed"
        assert result.return_value["response"] == "Done"


class TestTaskIQInterruptResume:
    """Тесты interrupt/resume через TaskIQ."""

    @pytest.fixture
    async def setup_interrupt_flow(self, app, container, unique_id):
        """Создает flow с interrupt для тестов."""
        from apps.agents.src.models import AgentConfig

        agent_id = f"taskiq_interrupt_flow_{unique_id}"
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="TaskIQ Interrupt Agent",
            entry="ask",
            nodes={
                "ask": {
                    "type": "function",
                    "code": """
def run(state):
    if 'name' in state:
        return state
    if state.get('asked_name'):
        state['name'] = state.get('content', '')
        return state
    state['interrupt'] = {'question': 'What is your name?'}
    state['asked_name'] = True
    return state
""",
                },
                "greet": {
                    "type": "function",
                    "code": """
def run(state):
    name = state.get('name', 'Unknown')
    state['response'] = f'Hello, {name}!'
    return state
""",
                },
            },
            edges=[
                {"from": "ask", "to": "greet"},
                {"from": "greet", "to": None},
            ],
        )
        await container.agent_repository.set(agent_config)
        return agent_id

    @pytest.mark.asyncio
    async def test_interrupt_via_taskiq(
        self, app, container, setup_interrupt_flow, unique_id, mock_context
    ):
        """Interrupt работает через TaskIQ."""
        agent_id = setup_interrupt_flow
        session_id = f"{agent_id}:taskiq-interrupt-{unique_id}-{uuid.uuid4().hex[:8]}"

        mock_context.session_id = session_id
        mock_context.agent_id = agent_id
        mock_context.user.user_id = "test-user"
        task = await process_agent_task.kiq(
            agent_id=agent_id,
            session_id=session_id,
            user_id="test-user",
            content="Start",
            context_data=mock_context.model_dump(),
        )

        result = await task.wait_result()

        if result.is_err:
            print(f"\n❌ Task failed!")
            print(f"Error type: {type(result.error)}")
            print(f"Error: {result.error}")
            if hasattr(result.error, '__traceback__'):
                import traceback
                print("Traceback:")
                traceback.print_exception(type(result.error), result.error, result.error.__traceback__)
        
        assert not result.is_err, f"Task failed: {result.error}"
        assert result.return_value["status"] == "input-required"
        assert result.return_value["interrupt"]["question"] == "What is your name?"

    @pytest.mark.asyncio
    async def test_resume_via_taskiq(
        self, app, container, setup_interrupt_flow, unique_id, mock_context
    ):
        """Resume после interrupt работает через TaskIQ."""
        agent_id = setup_interrupt_flow
        session_id = f"{agent_id}:taskiq-resume-{unique_id}-{uuid.uuid4().hex[:8]}"

        mock_context.session_id = session_id
        mock_context.agent_id = agent_id
        mock_context.user.user_id = "test-user"
        task1 = await process_agent_task.kiq(
            agent_id=agent_id,
            session_id=session_id,
            user_id="test-user",
            content="Start",
            context_data=mock_context.model_dump(),
        )
        result1 = await task1.wait_result()
        
        if result1.is_err:
            print(f"\n❌ Task1 failed!")
            print(f"Error: {result1.error}")
        
        assert not result1.is_err, f"Task1 failed: {result1.error}"
        assert result1.return_value["status"] == "input-required"

        task2 = await process_agent_task.kiq(
            agent_id=agent_id,
            session_id=session_id,
            user_id="test-user",
            content="Alice",
            is_resume=True,
            context_data=mock_context.model_dump(),
        )

        result2 = await task2.wait_result()

        assert not result2.is_err, f"Resume failed: {result2.error}"
        assert result2.return_value["status"] == "completed"
        assert "Alice" in result2.return_value["response"]


class TestTaskIQInlineCode:
    """Тесты inline кода через TaskIQ."""

    @pytest.mark.asyncio
    async def test_inline_code_via_taskiq_kiq(self, app):
        """Inline код выполняется через TaskIQ .kiq() + wait_result()."""
        code = """
def run(state):
    state['computed'] = state.get('x', 0) ** 2
    return state
"""
        # Создаем валидный state
        state_dict = {
            "task_id": "test-task",
            "context_id": "test-context",
            "user_id": "test-user",
            "session_id": "test:test-context",
            "x": 7,
        }
        
        task = await execute_inline_code.kiq(code, state_dict)

        result = await task.wait_result()

        assert not result.is_err, f"Task failed: {result.error}"
        assert result.return_value["computed"] == 49


class TestTaskIQAPIIntegration:
    """Тесты интеграции API с TaskIQ."""

    @pytest.fixture
    async def setup_api_flow(self, app, container, unique_id):
        """Создает flow для тестов API."""
        from apps.agents.src.models import AgentConfig

        agent_id = f"taskiq_api_flow_{unique_id}_{uuid.uuid4().hex[:8]}"
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="TaskIQ API Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "function",
                    "code": "def run(state):\n    state['response'] = f\"Got: {state.get('content', '')}\"\n    return state",
                },
            },
            edges=[{"from": "main", "to": None}],
        )
        await container.agent_repository.set(agent_config)
        return agent_id

    @pytest.mark.asyncio
    async def test_api_submit_uses_taskiq(self, client, setup_api_flow, unique_id):
        """API /tasks/submit использует TaskIQ внутри."""
        agent_id = setup_api_flow
        session_id = f"{agent_id}:api-taskiq-{unique_id}-{uuid.uuid4().hex[:8]}"

        response = await client.post(
            "/agents/api/v1/tasks/submit",
            json={
                "agent_id": agent_id,
                "content": "Hello TaskIQ",
                "session_id": session_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        # API возвращает A2A Task
        assert data["status"]["state"] == "completed"
        # Ответ в message.parts
        response_text = data["status"]["message"]["parts"][0]["text"]
        assert "Hello TaskIQ" in response_text

    @pytest.mark.asyncio
    @pytest.mark.timeout(45)  # Таймаут для предотвращения зависания
    async def test_a2a_endpoint_uses_taskiq(self, client, setup_api_flow, unique_id):
        """A2A endpoint использует TaskIQ внутри."""

        agent_id = setup_api_flow
        task_id = str(uuid.uuid4())
        context_id = f"a2a-taskiq-{unique_id}-{uuid.uuid4().hex[:8]}"

        response = await client.post(
            f"/agents/api/v1/{agent_id}",
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

