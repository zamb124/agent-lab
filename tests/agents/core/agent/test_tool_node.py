"""
Тесты для ToolNode.

ToolNode позволяет использовать BaseTool как ноду графа.
Поддерживает input_mapping для @state:, @var: и констант.
"""

import pytest
from typing import Any, Dict

from apps.agents.src.agent.nodes import ToolNode, create_node
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


class TestToolNode:
    """Тесты ToolNode."""

    @pytest.mark.asyncio
    async def test_tool_node_basic_execution(self):
        """ToolNode выполняет tool и сохраняет результат в state."""
        tool = SimpleTool()
        node = ToolNode(
            node_id="test_node",
            tool=tool,
            input_mapping={"x": 10, "y": 20},
            output_key="result",
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        assert result["result"] == 30

    @pytest.mark.asyncio
    async def test_tool_node_input_mapping_state(self):
        """ToolNode берет аргументы из state через @state:."""
        tool = SimpleTool()
        node = ToolNode(
            node_id="test_node",
            tool=tool,
            input_mapping={
                "x": "@state:value_x",
                "y": "@state:value_y",
            },
            output_key="sum",
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

        assert result["sum"] == 20

    @pytest.mark.asyncio
    async def test_tool_node_input_mapping_nested_state(self):
        """ToolNode берет аргументы из вложенного state через @state:path."""
        tool = SimpleTool()
        node = ToolNode(
            node_id="test_node",
            tool=tool,
            input_mapping={
                "x": "@state:data.first",
                "y": "@state:data.second",
            },
            output_key="total",
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

        assert result["total"] == 300

    @pytest.mark.asyncio
    async def test_tool_node_input_mapping_var(self):
        """ToolNode берет аргументы из переменных через @var:."""
        tool = SimpleTool()
        node = ToolNode(
            node_id="test_node",
            tool=tool,
            input_mapping={
                "x": "@var:multiplier",
                "y": "@state:value",
            },
            output_key="result",
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

        assert result["result"] == 15

    @pytest.mark.asyncio
    async def test_tool_node_input_mapping_constants(self):
        """ToolNode использует константы в input_mapping."""
        tool = SimpleTool()
        node = ToolNode(
            node_id="test_node",
            tool=tool,
            input_mapping={
                "x": 42,
                "y": 8,
            },
            output_key="answer",
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        assert result["answer"] == 50

    @pytest.mark.asyncio
    async def test_tool_node_mixed_mapping(self):
        """ToolNode поддерживает смешанный маппинг."""
        tool = FormatterTool()
        node = ToolNode(
            node_id="test_node",
            tool=tool,
            input_mapping={
                "template": "Привет, {name}!",
                "name": "@state:user.name",
            },
            output_key="greeting",
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

        assert result["greeting"] == "Привет, Иван!"

    @pytest.mark.asyncio
    async def test_tool_node_default_output_key(self):
        """ToolNode использует node_id как output_key по умолчанию."""
        tool = SimpleTool()
        node = ToolNode(
            node_id="my_calculator",
            tool=tool,
            input_mapping={"x": 1, "y": 2},
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        # По умолчанию output_key = node_id
        assert result["my_calculator"] == 3

    @pytest.mark.asyncio
    async def test_tool_node_preserves_state(self):
        """ToolNode сохраняет остальные поля state."""
        tool = SimpleTool()
        node = ToolNode(
            node_id="test_node",
            tool=tool,
            input_mapping={"x": 1, "y": 2},
            output_key="result",
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

        assert result["existing_field"] == "value"
        assert result["another"] == 123
        assert result["result"] == 3

    @pytest.mark.asyncio
    async def test_tool_node_mock(self):
        """ToolNode поддерживает mock через state.mock."""
        tool = SimpleTool()
        node = ToolNode(
            node_id="my_tool_node",
            tool=tool,
            input_mapping={"x": 1, "y": 2},
            # output_key по умолчанию = node_id = "my_tool_node"
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

        assert result["my_tool_node"] == 999
        assert result["mocked"] is True


class TestInlineToolNode:
    """Тесты ToolNode с InlineTool."""

    @pytest.mark.asyncio
    async def test_inline_tool_basic(self):
        """InlineTool выполняется через ToolNode."""
        inline_tool = InlineTool(
            tool_id="inline_add",
            code="def execute(args, state):\n    return args['a'] + args['b']",
            description="Сложение",
            parameters={
                "a": CallParameter(type="integer", description="Первое число"),
                "b": CallParameter(type="integer", description="Второе число"),
            },
        )

        node = ToolNode(
            node_id="inline_node",
            tool=inline_tool,
            input_mapping={"a": 100, "b": 200},
            output_key="sum",
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        assert result["sum"] == 300

    @pytest.mark.asyncio
    async def test_inline_tool_with_state_access(self):
        """InlineTool имеет доступ к state."""
        inline_tool = InlineTool(
            tool_id="state_reader",
            code="def execute(args, state):\n    return state.get('secret', 'not found')",
            description="Читает из state",
        )

        node = ToolNode(
            node_id="reader_node",
            tool=inline_tool,
            input_mapping={},
            output_key="secret_value",
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

        assert result["secret_value"] == "my_secret_value"

    @pytest.mark.asyncio
    async def test_inline_tool_with_var_mapping(self):
        """InlineTool с маппингом из переменных."""
        inline_tool = InlineTool(
            tool_id="greeting",
            code="def execute(args, state):\n    return f\"Добро пожаловать в {args['company']}, {args['user']}!\"",
            description="Приветствие",
        )

        node = ToolNode(
            node_id="greeting_node",
            tool=inline_tool,
            input_mapping={
                "company": "@var:company_name",
                "user": "@state:user.name",
            },
            output_key="message",
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

        assert result["message"] == "Добро пожаловать в Acme Corp, Мария!"


class TestCreateNodeTool:
    """Тесты create_node для type='tool'."""

    @pytest.mark.asyncio
    async def test_create_node_inline_tool(self):
        """create_node создает ToolNode из inline кода."""
        node_config = {
            "type": "tool",
            "code": "def execute(args, state):\n    return args['x'] * 2",
            "args_schema": {
                "x": {"type": "integer", "description": "Число для удвоения"},
            },
            "input_mapping": {"x": 5},
            "output_key": "doubled",
        }

        node = await create_node("double_node", node_config)

        assert isinstance(node, ToolNode)
        assert node.node_id == "double_node"
        assert node.output_key == "doubled"

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)
        assert result["doubled"] == 10

    @pytest.mark.asyncio
    async def test_create_node_inline_tool_with_mapping(self):
        """create_node c inline tool и input_mapping."""
        node_config = {
            "type": "tool",
            "code": "def execute(args, state):\n    return f\"{args['prefix']}{args['value']}\"",
            "input_mapping": {
                "prefix": "@var:order_prefix",
                "value": "@state:order_id",
            },
            "output_key": "formatted_order",
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

        assert result["formatted_order"] == "ORD-12345"

