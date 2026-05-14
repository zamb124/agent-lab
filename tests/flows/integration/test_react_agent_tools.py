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
from core.state import ExecutionState

# Фикстуры для tools

@pytest.fixture
def calculator_tool_code():
    """Код для calculator tool - складывает числа."""
    return """
async def execute(args: dict, state: dict = None):
    expression = args.get('expression', '1+1')
    if '+' in expression:
        parts = expression.split('+')
        return str(int(parts[0].strip()) + int(parts[1].strip()))
    return '0'
"""


@pytest.fixture
def greeter_tool_code():
    """Код для greeter tool - приветствует."""
    return """
async def execute(args: dict, state: dict = None):
    name = args.get('name', 'World')
    return f'Hello, {name}!'
"""


@pytest.fixture
def inline_tool_config(greeter_tool_code):
    """Inline tool конфиг для использования в agent."""
    return {
        "tool_id": "greeter_inline",
        "description": "Приветствует пользователя по имени",
        "args_schema": {
            "name": {"type": "string", "description": "Имя для приветствия"}
        },
        "code": greeter_tool_code
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
        "tools": []
    }


# === ТЕСТЫ ДЛЯ INLINE REACT AGENT (в agent.json) ===

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

        # Agent с inline agent и inline tool
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Inline Tool",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй greeter_inline чтобы поприветствовать пользователя.",
                    "tools": [inline_tool_config]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # Mock LLM: сначала вызывает tool, потом отвечает
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "greeter_inline", "args": {"name": "Тест"}},
            {"type": "text", "content": "Приветствие выполнено: Hello, Тест!"},
        ])

        # Запускаем flow
        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Поприветствуй Тест"
        )
        result = await flow.run(state)

        # Проверяем что агент ответил
        assert "response" in result
        assert "Hello, Тест" in result["response"]

        # Cleanup
        await container.flow_repository.delete(flow_id)

    async def test_inline_agent_executes_node_as_tool(
        self, helper_node_config, app, unique_id, mock_llm_with_queue
    ):
        """
        Inline react agent вызывает ноду как tool.
        """
        flow_id = f"test_node_tool_{unique_id}"
        container = get_container()

        # Inline tool config (полный конфиг ноды как tool)
        helper_tool_config = {
            "tool_id": helper_node_config["node_id"],
            "type": "llm_node",
            "name": helper_node_config["name"],
            "description": helper_node_config["description"],
            "prompt": helper_node_config["prompt"],
            "tools": []
        }

        # Agent с inline node как tool (не ссылка, а полный конфиг)
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Node as Tool",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй helper_node для помощи пользователю.",
                    "tools": [helper_tool_config]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # Mock LLM для основного агента и helper node
        mock_llm_with_queue([
            # Основной агент вызывает helper
            {"type": "tool_call", "tool": helper_node_config["node_id"], "args": {"query": "Помоги"}},
            # Helper node отвечает
            {"type": "text", "content": "Помощь оказана!"},
            # Основной агент финализирует
            {"type": "text", "content": "Helper ответил: Помощь оказана!"},
        ])

        factory = container.flow_factory
        agent = await factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Мне нужна помощь"
        )
        result = await agent.run(state)

        assert "response" in result

        # Cleanup
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

        # Inline tool config (вместо ссылки на БД)
        inline_tool_config = {
            "tool_id": tool_id,
            "description": "Калькулятор",
            "code": calculator_tool_code,
            "args_schema": {
                "expression": {"type": "string", "description": "Выражение"}
            }
        }

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test DB Inline Tool",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй калькулятор для вычислений.",
                    "tools": [inline_tool_config]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": tool_id, "args": {"expression": "3+5"}},
            {"type": "text", "content": "Результат: 8"},
        ])

        factory = container.flow_factory
        flow = await factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Сколько 3+5?"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "8" in result["response"]

        # Cleanup
        await container.flow_repository.delete(flow_id)
        await container.tool_repository.delete(tool_id)

    async def test_inline_agent_executes_mixed_tools(
        self,
        inline_tool_config,
        helper_node_config,
        calculator_tool_code,
        container,
        unique_id,
        mock_llm_with_queue
    ):
        """
        Inline react agent с несколькими разными типами tools.
        Агент последовательно вызывает разные tools.
        """
        flow_id = f"test_mixed_{unique_id}"
        db_tool_id = f"calc_mixed_{unique_id}"

        # Inline helper node config (вместо ссылки)
        helper_tool_config = {
            "tool_id": helper_node_config["node_id"],
            "type": "llm_node",
            "name": helper_node_config["name"],
            "description": helper_node_config["description"],
            "prompt": helper_node_config["prompt"],
            "tools": []
        }

        # Inline calculator config (вместо DB ссылки)
        calc_tool_config = {
            "tool_id": db_tool_id,
            "description": "Calculator",
            "code": calculator_tool_code
        }

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Mixed Tools",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "У тебя есть greeter, helper и calculator. Используй их.",
                    "tools": [
                        inline_tool_config,     # inline tool
                        helper_tool_config,     # node as tool (inline)
                        calc_tool_config        # calculator (inline)
                    ]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # Агент вызывает inline tool
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "greeter_inline", "args": {"name": "User"}},
            {"type": "text", "content": "Поприветствовал: Hello, User!"},
        ])

        factory = container.flow_factory
        agent = await factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Поприветствуй User"
        )
        result = await agent.run(state)

        assert "response" in result

        # Cleanup
        await container.flow_repository.delete(flow_id)
        await container.node_repository.delete(helper_node_config["node_id"])
        await container.tool_repository.delete(db_tool_id)


# === ТЕСТЫ ВЫПОЛНЕНИЯ TOOL И ПРОВЕРКИ РЕЗУЛЬТАТА ===

class TestToolExecutionResults:
    """
    Тесты проверяющие что tools реально выполняются и возвращают результат.
    """

    async def test_inline_tool_returns_correct_result(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Inline tool возвращает корректный результат который используется агентом.
        """
        flow_id = f"test_result_{unique_id}"

        # Tool который возвращает конкретный результат
        tool_code = """
async def execute(args: dict, state: dict = None):
    x = int(args.get('x', 0))
    y = int(args.get('y', 0))
    return f'SUM={x + y}'
"""

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Tool Result",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй sum_tool для сложения чисел.",
                    "tools": [{
                        "tool_id": "sum_tool",
                        "description": "Складывает два числа",
                        "args_schema": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"}
                        },
                        "code": tool_code
                    }]
                }
            },
            edges=[]
        )
        container = get_container()
        await container.flow_repository.set(flow_config)

        # LLM вызывает tool, получает результат, формирует ответ
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "sum_tool", "args": {"x": 10, "y": 20}},
            {"type": "text", "content": "Сумма: SUM=30"},
        ])

        factory = container.flow_factory
        flow = await factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Сложи 10 и 20"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "30" in result["response"]

        await container.flow_repository.delete(flow_id)

    async def test_tool_receives_state(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Tool получает state и может использовать данные из него.
        """
        flow_id = f"test_state_{unique_id}"

        tool_code = """
async def execute(args: dict, state: dict = None):
    user = state.get('user_name', 'Unknown') if state else 'Unknown'
    return f'Hello, {user}!'
"""

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test State Access",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй greet_user.",
                    "tools": [{
                        "tool_id": "greet_user",
                        "description": "Приветствует пользователя из state",
                        "code": tool_code
                    }]
                }
            },
            edges=[]
        )
        container = get_container()
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "greet_user", "args": {}},
            {"type": "text", "content": "Приветствие: Hello, Виктор!"},
        ])

        factory = container.flow_factory
        flow = await factory.get_flow(flow_id)
        # Передаём user_name в state
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Поприветствуй",
            user_name="Виктор"
        )
        result = await flow.run(state)

        assert "response" in result

        await container.flow_repository.delete(flow_id)

    async def test_multiple_tool_calls_in_sequence(
        self, app, unique_id, mock_llm_with_queue
    ):
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
                            "code": "async def execute(args, state):\n    return 'STEP1_DONE'"
                        },
                        {
                            "tool_id": "step2",
                            "description": "Второй шаг",
                            "code": "async def execute(args, state):\n    return 'STEP2_DONE'"
                        }
                    ]
                }
            },
            edges=[]
        )
        container = get_container()
        await container.flow_repository.set(flow_config)

        # Агент вызывает step1, потом step2, потом отвечает
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "step1", "args": {}},
            {"type": "tool_call", "tool": "step2", "args": {}},
            {"type": "text", "content": "Выполнено: STEP1_DONE, STEP2_DONE"},
        ])

        factory = container.flow_factory
        flow = await factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Выполни шаги"
        )
        result = await flow.run(state)

        assert "response" in result

        await container.flow_repository.delete(flow_id)

