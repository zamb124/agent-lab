"""
Тесты для CodeNode.

CodeNode позволяет использовать BaseTool как ноду графа.
Поддерживает input_mapping для @state:, @var: и констант.
Поддерживает функции с именованными аргументами и дефолтами.
"""

import pytest
from typing import Any, Dict

from apps.agents.src.agent.nodes import CodeNode, create_node
from apps.agents.src.mapping import MappingResolver
from apps.agents.src.tools.base import BaseTool, InlineTool
from apps.agents.src.models.tool_reference import CallParameter


class SimpleTool(BaseTool):
    """Тестовый tool для unit-тестов."""

    name = "simple_tool"
    description = "Простой тестовый tool"

    async def _run_impl(self, args: Dict[str, Any], state: Dict[str, Any]) -> Any:
        """Возвращает сумму x и y из args."""
        x = args.get("x", 0)
        y = args.get("y", 0)
        return x + y


class FormatterTool(BaseTool):
    """Tool для форматирования строк."""

    name = "formatter_tool"
    description = "Форматирует строку"

    async def _run_impl(self, args: Dict[str, Any], state: Dict[str, Any]) -> Any:
        """Форматирует шаблон с переменными."""
        template = args.get("template", "")
        name = args.get("name", "")
        return template.format(name=name)


class TestCodeNode:
    """Тесты CodeNode."""

    @pytest.mark.asyncio
    async def test_tool_node_basic_execution(self):
        """CodeNode выполняет tool и сохраняет результат в state."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(args, state):
    x = args.get("x", 0)
    y = args.get("y", 0)
    return {"result": x + y}""",
                "input_mapping": {"x": 10, "y": 20},
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        assert result.result == 30

    @pytest.mark.asyncio
    async def test_tool_node_input_mapping_state(self):
        """CodeNode берет аргументы из state через @state:."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(args, state):
    x = args.get("x", 0)
    y = args.get("y", 0)
    return {"sum": x + y}""",
                "input_mapping": {
                    "x": "@state:value_x",
                    "y": "@state:value_y",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            value_x=5,
            value_y=15
        )
        result = await node.run(state)

        assert result.sum == 20

    @pytest.mark.asyncio
    async def test_tool_node_input_mapping_nested_state(self):
        """CodeNode берет аргументы из вложенного state через @state:path."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(args, state):
    x = args.get("x", 0)
    y = args.get("y", 0)
    return {"total": x + y}""",
                "input_mapping": {
                    "x": "@state:data.first",
                    "y": "@state:data.second",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            data={"first": 100, "second": 200}
        )
        result = await node.run(state)

        assert result.total == 300

    @pytest.mark.asyncio
    async def test_tool_node_input_mapping_var(self):
        """CodeNode берет аргументы из переменных через @var:."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(args, state):
    x = args.get("x", 0)
    y = args.get("y", 0)
    return {"result": x + y}""",
                "input_mapping": {
                    "x": "@var:multiplier",
                    "y": "@state:value",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            value=10,
            variables={"multiplier": 5}
        )
        result = await node.run(state)

        assert result.result == 15

    @pytest.mark.asyncio
    async def test_tool_node_input_mapping_constants(self):
        """CodeNode использует константы в input_mapping."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(args, state):
    x = args.get("x", 0)
    y = args.get("y", 0)
    return {"answer": x + y}""",
                "input_mapping": {
                    "x": 42,
                    "y": 8,
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        assert result.answer == 50

    @pytest.mark.asyncio
    async def test_tool_node_mixed_mapping(self):
        """CodeNode поддерживает смешанный маппинг."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(args, state):
    template = args.get("template", "")
    name = args.get("name", "")
    return {"greeting": template.format(name=name)}""",
                "input_mapping": {
                    "template": "Привет, {name}!",
                    "name": "@state:user.name",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user={"name": "Иван"}
        )
        result = await node.run(state)

        assert result.greeting == "Привет, Иван!"

    @pytest.mark.asyncio
    async def test_tool_node_without_output_key(self):
        """CodeNode без output_mapping записывает скалярный результат в state.result."""
        node = CodeNode(
            node_id="my_calculator",
            config={
                "code": """def execute(args, state):
    x = args.get("x", 0)
    y = args.get("y", 0)
    return x + y""",
                "input_mapping": {"x": 1, "y": 2},
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        assert result.result == 3

    @pytest.mark.asyncio
    async def test_tool_node_preserves_state(self):
        """CodeNode сохраняет остальные поля state."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(args, state):
    x = args.get("x", 0)
    y = args.get("y", 0)
    return {"result": x + y}""",
                "input_mapping": {"x": 1, "y": 2},
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            existing_field="value",
            another=123
        )
        result = await node.run(state)

        assert result.existing_field == "value"
        assert result.another == 123
        assert result.result == 3

    @pytest.mark.asyncio
    async def test_tool_node_mock(self):
        """CodeNode поддерживает mock через state.mock."""
        node = CodeNode(
            node_id="my_tool_node",
            config={
                "code": """def execute(args, state):
    x = args.get("x", 0)
    y = args.get("y", 0)
    return x + y""",
                "input_mapping": {"x": 1, "y": 2},
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "nodes": {
                    "my_tool_node": {"my_tool_node": 999, "mocked": True}
                }
            }
        )
        result = await node.run(state)

        assert result.my_tool_node == 999
        assert result.mocked is True


class TestInlineCodeNode:
    """Тесты CodeNode с inline кодом."""

    @pytest.mark.asyncio
    async def test_inline_tool_basic(self):
        """CodeNode выполняет inline код."""
        node = CodeNode(
            node_id="inline_node",
            config={
                "code": "def execute(args, state):\n    return {'sum': args['a'] + args['b']}",
                "input_mapping": {"a": 100, "b": 200},
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        assert result.sum == 300

    @pytest.mark.asyncio
    async def test_inline_tool_with_state_access(self):
        """CodeNode имеет доступ к state."""
        node = CodeNode(
            node_id="reader_node",
            config={
                "code": "def execute(args, state):\n    return {'secret_value': state.get('secret', 'not found')}",
                "input_mapping": {},
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            secret="my_secret_value"
        )
        result = await node.run(state)

        assert result.secret_value == "my_secret_value"

    @pytest.mark.asyncio
    async def test_inline_tool_with_var_mapping(self):
        """CodeNode с маппингом из переменных."""
        node = CodeNode(
            node_id="greeting_node",
            config={
                "code": "def execute(args, state):\n    return {'message': f\"Добро пожаловать в {args['company']}, {args['user']}!\"}",
                "input_mapping": {
                    "company": "@var:company_name",
                    "user": "@state:user.name",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user={"name": "Мария"},
            variables={"company_name": "Acme Corp"}
        )
        result = await node.run(state)

        assert result.message == "Добро пожаловать в Acme Corp, Мария!"


class TestCreateNodeTool:
    """Тесты create_node для type='tool'."""

    @pytest.mark.asyncio
    async def test_create_node_inline_tool(self):
        """create_node создает CodeNode из inline кода."""
        node_config = {
            "type": "code",
            "code": "def execute(args, state):\n    return {'doubled': args['x'] * 2}",
            "args_schema": {
                "x": {"type": "integer", "description": "Число для удвоения"},
            },
            "input_mapping": {"x": 5},
        }

        node = await create_node("double_node", node_config)

        assert isinstance(node, CodeNode)
        assert node.node_id == "double_node"

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)
        assert result.doubled == 10

    @pytest.mark.asyncio
    async def test_create_node_inline_tool_with_mapping(self):
        """create_node c inline tool и input_mapping."""
        node_config = {
            "type": "code",
            "code": "def execute(args, state):\n    return {'formatted_order': f\"{args['prefix']}{args['value']}\"}",
            "input_mapping": {
                "prefix": "@var:order_prefix",
                "value": "@state:order_id",
            },
        }

        node = await create_node("format_node", node_config)
        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            order_id="12345",
            variables={"order_prefix": "ORD-"}
        )
        result = await node.run(state)

        assert result.formatted_order == "ORD-12345"


class TestCodeNodeNamedArguments:
    """Тесты CodeNode с именованными аргументами и дефолтами."""

    @pytest.mark.asyncio
    async def test_named_arguments_with_defaults(self):
        """CodeNode с функцией, имеющей именованные аргументы и дефолты."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20, state=None):
    return {"result": x + y}""",
                "input_mapping": {},
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        # Должны использоваться дефолтные значения
        assert result.result == 30  # 10 + 20

    @pytest.mark.asyncio
    async def test_named_arguments_from_input_mapping(self):
        """CodeNode: именованные аргументы подставляются из input_mapping."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20, state=None):
    return {"result": x + y}""",
                "input_mapping": {
                    "x": 5,
                    "y": 15,
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        # Должны использоваться значения из input_mapping
        assert result.result == 20  # 5 + 15

    @pytest.mark.asyncio
    async def test_named_arguments_partial_defaults(self):
        """CodeNode: часть аргументов из input_mapping, часть из дефолтов."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20, z=30, state=None):
    return {"result": x + y + z}""",
                "input_mapping": {
                    "x": 5,
                    # y и z должны взять дефолты
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        # x из input_mapping, y и z из дефолтов
        assert result.result == 55  # 5 + 20 + 30

    @pytest.mark.asyncio
    async def test_named_arguments_from_state(self):
        """CodeNode: именованные аргументы подставляются из state через @state:."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20, state=None):
    return {"result": x + y}""",
                "input_mapping": {
                    "x": "@state:value_x",
                    "y": "@state:value_y",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            value_x=7,
            value_y=13,
        )
        result = await node.run(state)

        # Должны использоваться значения из state
        assert result.result == 20  # 7 + 13

    @pytest.mark.asyncio
    async def test_named_arguments_mixed_sources(self):
        """CodeNode: смешанные источники - state, переменные, константы, дефолты."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20, z=30, multiplier=1, state=None):
    return {"result": (x + y + z) * multiplier}""",
                "input_mapping": {
                    "x": "@state:value_x",
                    "y": "@var:value_y",
                    "z": 100,  # константа
                    # multiplier должен взять дефолт
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            value_x=5,
            variables={"value_y": 15},
        )
        result = await node.run(state)

        # x из state (5), y из variables (15), z константа (100), multiplier дефолт (1)
        assert result.result == 120  # (5 + 15 + 100) * 1

    @pytest.mark.asyncio
    async def test_named_arguments_with_state_parameter(self):
        """CodeNode: функция с именованными аргументами и параметром state."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20, state=None):
    # Используем state для доступа к дополнительным данным
    bonus = getattr(state, 'bonus', 0) if state else 0
    return {"result": x + y + bonus}""",
                "input_mapping": {
                    "x": "@state:value_x",
                    "y": "@state:value_y",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            value_x=5,
            value_y=15,
            bonus=10,
        )
        result = await node.run(state)

        # x и y из state, bonus из state напрямую
        assert result.result == 30  # 5 + 15 + 10

    @pytest.mark.asyncio
    async def test_named_arguments_string_defaults(self):
        """CodeNode: именованные аргументы со строковыми дефолтами."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(greeting="Hello", name="World", state=None):
    return {"message": f"{greeting}, {name}!"}""",
                "input_mapping": {
                    "name": "@state:user_name",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user_name="Иван",
        )
        result = await node.run(state)

        # greeting из дефолта, name из state
        assert result.message == "Hello, Иван!"

    @pytest.mark.asyncio
    async def test_named_arguments_none_default(self):
        """CodeNode: именованные аргументы с None в дефолте."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(value=None, multiplier=1, state=None):
    if value is None:
        value = 0
    return {"result": value * multiplier}""",
                "input_mapping": {
                    "value": "@state:input_value",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            input_value=42,
        )
        result = await node.run(state)

        # value из state, multiplier из дефолта
        assert result.result == 42  # 42 * 1

    @pytest.mark.asyncio
    async def test_named_arguments_list_default(self):
        """CodeNode: именованные аргументы со списком в дефолте."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(items=None, prefix="Item", state=None):
    if items is None:
        items = []
    return {"formatted": [f"{prefix}: {item}" for item in items]}""",
                "input_mapping": {
                    "items": "@state:item_list",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            item_list=["apple", "banana"],
        )
        result = await node.run(state)

        # items из state, prefix из дефолта
        assert result.formatted == ["Item: apple", "Item: banana"]

    @pytest.mark.asyncio
    async def test_named_arguments_dict_default(self):
        """CodeNode: именованные аргументы со словарем в дефолте."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(config=None, key="default", state=None):
    if config is None:
        config = {}
    return {"value": config.get(key, "not_found")}""",
                "input_mapping": {
                    "config": "@state:user_config",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user_config={"default": "found", "other": "value"},
        )
        result = await node.run(state)

        # config из state, key из дефолта
        assert result.value == "found"

    @pytest.mark.asyncio
    async def test_named_arguments_without_state_parameter(self):
        """CodeNode: функция с именованными аргументами без параметра state."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20):
    return {"result": x + y}""",
                "input_mapping": {
                    "x": "@state:value_x",
                    "y": "@state:value_y",
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            value_x=7,
            value_y=13,
        )
        result = await node.run(state)

        # Должны использоваться значения из state через input_mapping
        assert result.result == 20  # 7 + 13

    @pytest.mark.asyncio
    async def test_named_arguments_without_state_parameter_defaults_only(self):
        """CodeNode: функция без state, только дефолты используются."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20):
    return {"result": x + y}""",
                "input_mapping": {},
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        # Должны использоваться только дефолтные значения
        assert result.result == 30  # 10 + 20

    @pytest.mark.asyncio
    async def test_named_arguments_without_state_parameter_partial_mapping(self):
        """CodeNode: функция без state, часть аргументов из mapping, часть из дефолтов."""
        node = CodeNode(
            node_id="test_node",
            config={
                "code": """def execute(x=10, y=20, z=30):
    return {"result": x + y + z}""",
                "input_mapping": {
                    "x": 5,
                    # y и z должны взять дефолты
                },
            },
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        # x из input_mapping, y и z из дефолтов
        assert result.result == 55  # 5 + 20 + 30
