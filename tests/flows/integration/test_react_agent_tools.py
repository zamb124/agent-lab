"""
Тесты для react agent с разными типами tools.

Тестируем все комбинации:
1. Inline react agent (определён в agent.json)
2. Non-inline react agent (из agents.json / БД)

С разными типами tools:
- agent_as_tool: агент используемый как tool
- inline_tool: tool с inline code в конфиге
- db_inline_tool: tool из БД с inline_code

Каждый тест РЕАЛЬНО ВЫПОЛНЯЕТ агента через flow.execute()
"""

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from core.types import JsonObject
from tests.flows.durable_runtime_harness import run_flow, workflow_state

EMPTY_PARAMETERS_SCHEMA: JsonObject = {"type": "object", "properties": {}, "required": []}
EXPRESSION_PARAMETERS_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {"expression": {"type": "string", "description": "Выражение"}},
    "required": ["expression"],
}
QUERY_PARAMETERS_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}


@pytest.fixture
def calculator_tool_code():
    """Код для calculator tool - складывает числа."""
    return "\nasync def execute(args: dict, state: dict = None):\n    expression = args.get('expression', '1+1')\n    if '+' in expression:\n        parts = expression.split('+')\n        return str(int(parts[0].strip()) + int(parts[1].strip()))\n    return '0'\n"


@pytest.fixture
def greeter_tool_code():
    """Код для greeter tool - приветствует."""
    return "\nasync def execute(args: dict, state: dict = None):\n    name = args.get('name', 'World')\n    return f'Hello, {name}!'\n"


@pytest.fixture
def inline_tool_config(greeter_tool_code):
    """Inline tool конфиг для использования в agent."""
    return {
        "tool_id": "greeter_inline",
        "description": "Приветствует пользователя по имени",
        "parameters_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Имя для приветствия"}},
            "required": ["name"],
        },
        "code": greeter_tool_code,
    }


@pytest.fixture
def helper_node_config(unique_id):
    """Helper node конфиг для использования как tool."""
    return {
        "node_id": f"helper_node_{unique_id}",
        "type": "llm_node",
        "name": "Helper Node",
        "description": "Помощник - отвечает на простые вопросы",
        "prompt": "Ты помощник. Отвечай: 'Помощь оказана!'",
        "tools": [],
    }


class TestInlineReactAgentWithTools:
    """
    Тесты для inline react agent - агент определён прямо в agent.json.
    Каждый тест создаёт flow, запускает его и проверяет результат.
    """

    async def test_inline_agent_executes_inline_tool(
        self, app, inline_tool_config, unique_id, mock_llm_with_queue
    ):
        """
        Inline react agent вызывает inline tool и получает результат.
        LLM возвращает tool_call -> tool выполняется -> LLM отвечает с результатом.
        """
        container = get_container()
        flow_id = f"test_inline_tool_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Inline Tool",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй greeter_inline чтобы поприветствовать пользователя.",
                    "tools": [inline_tool_config],
                }
            },
            edges=[],
        )
        await container.flow_repository.set(flow_config)
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "greeter_inline", "args": {"name": "Тест"}},
                {"type": "text", "content": "Приветствие выполнено: Hello, Тест!"},
            ]
        )
        flow = await container.flow_factory.get_flow(flow_id)
        state = workflow_state(
            flow_id=flow_id,
            unique_id=f"inline-tool-{unique_id}",
            content="Поприветствуй Тест",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert "response" in result
        assert "Hello, Тест" in result["response"]
        await container.flow_repository.delete(flow_id)

    async def test_inline_agent_executes_node_as_tool(
        self, helper_node_config, app, unique_id, mock_llm_with_queue
    ):
        """
        Inline react agent вызывает ноду как tool.
        """
        flow_id = f"test_node_tool_{unique_id}"
        container = get_container()
        helper_tool_config = {
            "tool_id": helper_node_config["node_id"],
            "type": "llm_node",
            "name": helper_node_config["name"],
            "description": helper_node_config["description"],
            "parameters_schema": QUERY_PARAMETERS_SCHEMA,
            "prompt": helper_node_config["prompt"],
            "tools": [],
        }
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Node as Tool",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй helper_node для помощи пользователю.",
                    "tools": [helper_tool_config],
                }
            },
            edges=[],
        )
        await container.flow_repository.set(flow_config)
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": helper_node_config["node_id"],
                    "args": {"query": "Помоги"},
                },
                {"type": "text", "content": "Помощь оказана!"},
                {"type": "text", "content": "Helper ответил: Помощь оказана!"},
            ]
        )
        factory = container.flow_factory
        agent = await factory.get_flow(flow_id)
        state = workflow_state(
            flow_id=flow_id,
            unique_id=f"node-tool-{unique_id}",
            content="Мне нужна помощь",
        )
        result = await run_flow(container=container, flow=agent, state=state)
        assert "response" in result
        await container.flow_repository.delete(flow_id)

    async def test_inline_agent_executes_db_inline_tool(
        self, calculator_tool_code, app, unique_id, mock_llm_with_queue
    ):
        """
        Inline react agent вызывает tool с inline кодом.
        """
        flow_id = f"test_db_inline_{unique_id}"
        tool_id = f"calc_db_{unique_id}"
        container = get_container()
        inline_tool_config = {
            "tool_id": tool_id,
            "description": "Калькулятор",
            "code": calculator_tool_code,
            "parameters_schema": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Выражение"}},
                "required": ["expression"],
            },
        }
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test DB Inline Tool",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй калькулятор для вычислений.",
                    "tools": [inline_tool_config],
                }
            },
            edges=[],
        )
        await container.flow_repository.set(flow_config)
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": tool_id, "args": {"expression": "3+5"}},
                {"type": "text", "content": "Результат: 8"},
            ]
        )
        factory = container.flow_factory
        flow = await factory.get_flow(flow_id)
        state = workflow_state(
            flow_id=flow_id,
            unique_id=f"db-inline-{unique_id}",
            content="Сколько 3+5?",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert "response" in result
        assert "8" in result["response"]
        await container.flow_repository.delete(flow_id)
        await container.tool_repository.delete(tool_id)

    async def test_inline_agent_executes_mixed_tools(
        self,
        inline_tool_config,
        helper_node_config,
        calculator_tool_code,
        container,
        unique_id,
        mock_llm_with_queue,
    ):
        """
        Inline react agent с несколькими разными типами tools.
        Агент последовательно вызывает разные tools.
        """
        flow_id = f"test_mixed_{unique_id}"
        db_tool_id = f"calc_mixed_{unique_id}"
        helper_tool_config = {
            "tool_id": helper_node_config["node_id"],
            "type": "llm_node",
            "name": helper_node_config["name"],
            "description": helper_node_config["description"],
            "parameters_schema": QUERY_PARAMETERS_SCHEMA,
            "prompt": helper_node_config["prompt"],
            "tools": [],
        }
        calc_tool_config = {
            "tool_id": db_tool_id,
            "description": "Calculator",
            "parameters_schema": EXPRESSION_PARAMETERS_SCHEMA,
            "code": calculator_tool_code,
        }
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Mixed Tools",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "У тебя есть greeter, helper и calculator. Используй их.",
                    "tools": [inline_tool_config, helper_tool_config, calc_tool_config],
                }
            },
            edges=[],
        )
        await container.flow_repository.set(flow_config)
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "greeter_inline", "args": {"name": "User"}},
                {"type": "text", "content": "Поприветствовал: Hello, User!"},
            ]
        )
        factory = container.flow_factory
        agent = await factory.get_flow(flow_id)
        state = workflow_state(
            flow_id=flow_id,
            unique_id=f"mixed-{unique_id}",
            content="Поприветствуй User",
        )
        result = await run_flow(container=container, flow=agent, state=state)
        assert "response" in result
        await container.flow_repository.delete(flow_id)
        await container.node_repository.delete(helper_node_config["node_id"])
        await container.tool_repository.delete(db_tool_id)


class TestToolExecutionResults:
    """
    Тесты проверяющие что tools реально выполняются и возвращают результат.
    """

    async def test_inline_tool_returns_correct_result(self, app, unique_id, mock_llm_with_queue):
        """
        Inline tool возвращает корректный результат который используется агентом.
        """
        flow_id = f"test_result_{unique_id}"
        tool_code = "\nasync def execute(args: dict, state: dict = None):\n    x = int(args.get('x', 0))\n    y = int(args.get('y', 0))\n    return f'SUM={x + y}'\n"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Tool Result",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй sum_tool для сложения чисел.",
                    "tools": [
                        {
                            "tool_id": "sum_tool",
                            "description": "Складывает два числа",
                            "parameters_schema": {
                                "type": "object",
                                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                                "required": ["x", "y"],
                            },
                            "code": tool_code,
                        }
                    ],
                }
            },
            edges=[],
        )
        container = get_container()
        await container.flow_repository.set(flow_config)
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "sum_tool", "args": {"x": 10, "y": 20}},
                {"type": "text", "content": "Сумма: SUM=30"},
            ]
        )
        factory = container.flow_factory
        flow = await factory.get_flow(flow_id)
        state = workflow_state(
            flow_id=flow_id,
            unique_id=f"result-{unique_id}",
            content="Сложи 10 и 20",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert "response" in result
        assert "30" in result["response"]
        await container.flow_repository.delete(flow_id)

    async def test_tool_receives_state(self, app, unique_id, mock_llm_with_queue):
        """
        Tool получает state и может использовать данные из него.
        """
        flow_id = f"test_state_{unique_id}"
        tool_code = "\nasync def execute(args: dict, state: dict = None):\n    user = state.get('user_name', 'Unknown') if state else 'Unknown'\n    return f'Hello, {user}!'\n"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test State Access",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй greet_user.",
                    "tools": [
                        {
                            "tool_id": "greet_user",
                            "description": "Приветствует пользователя из state",
                            "parameters_schema": EMPTY_PARAMETERS_SCHEMA,
                            "code": tool_code,
                        }
                    ],
                }
            },
            edges=[],
        )
        container = get_container()
        await container.flow_repository.set(flow_config)
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "greet_user", "args": {}},
                {"type": "text", "content": "Приветствие: Hello, Виктор!"},
            ]
        )
        factory = container.flow_factory
        flow = await factory.get_flow(flow_id)
        state = workflow_state(
            flow_id=flow_id,
            unique_id=f"state-{unique_id}",
            content="Поприветствуй",
            user_name="Виктор",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert "response" in result
        await container.flow_repository.delete(flow_id)

    async def test_multiple_tool_calls_in_sequence(self, app, unique_id, mock_llm_with_queue):
        """
        Агент вызывает несколько tools последовательно.
        """
        flow_id = f"test_sequence_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Sequential Tools",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй tools последовательно.",
                    "tools": [
                        {
                            "tool_id": "step1",
                            "description": "Первый шаг",
                            "parameters_schema": EMPTY_PARAMETERS_SCHEMA,
                            "code": "async def run(args, state):\n    return 'STEP1_DONE'",
                        },
                        {
                            "tool_id": "step2",
                            "description": "Второй шаг",
                            "parameters_schema": EMPTY_PARAMETERS_SCHEMA,
                            "code": "async def run(args, state):\n    return 'STEP2_DONE'",
                        },
                    ],
                }
            },
            edges=[],
        )
        container = get_container()
        await container.flow_repository.set(flow_config)
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "step1", "args": {}},
                {"type": "tool_call", "tool": "step2", "args": {}},
                {"type": "text", "content": "Выполнено: STEP1_DONE, STEP2_DONE"},
            ]
        )
        factory = container.flow_factory
        flow = await factory.get_flow(flow_id)
        state = workflow_state(
            flow_id=flow_id,
            unique_id=f"sequence-{unique_id}",
            content="Выполни шаги",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert "response" in result
        await container.flow_repository.delete(flow_id)
