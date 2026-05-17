"""
Интеграционные тесты для inline tools в агентах.

Тестирует LlmNode с inline tool конфигами (dict).
"""

import pytest

from apps.flows.src.tools.code_tool import CodeTool
from core.state import ExecutionState


class TestToolRegistryInlineConfig:
    """Тесты ToolRegistry с inline tool конфигами."""

    @pytest.mark.asyncio
    async def test_get_tool_from_dict_config(self, container):
        """ToolRegistry создает CodeTool из dict конфига."""
        config = {
            "tool_id": "inline_calculator",
            "description": "Простой калькулятор",
            "args_schema": {
                "a": {"type": "integer", "description": "Первое число"},
                "b": {"type": "integer", "description": "Второе число"},
            },
            "code": "async def run(args, state):\n    return args['a'] + args['b']",
        }

        tool = await container.tool_registry.create_tool(config)

        assert isinstance(tool, CodeTool)
        assert tool.name == "inline_calculator"
        assert tool.description == "Простой калькулятор"

        # Проверяем выполнение
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({"a": 10, "b": 20}, state)
        assert result == 30

    @pytest.mark.asyncio
    async def test_get_tool_from_dict_minimal(self, container):
        """ToolRegistry создает CodeTool из минимального dict."""
        config = {
            "tool_id": "simple",
            "code": "async def run(args, state):\n    return 'ok'",
        }

        tool = await container.tool_registry.create_tool(config)

        assert isinstance(tool, CodeTool)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({}, state)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_create_tools_string_raises_error(self, container):
        """ToolRegistry выбрасывает ошибку для строковых tool ID."""
        tools_config = [
            "calculator",  # строка - должна быть инлайнена через FlowsLoader
        ]

        with pytest.raises(ValueError, match="passed as string"):
            await container.tool_registry.create_tools(tools_config)

    @pytest.mark.asyncio
    async def test_create_tools_inline_list(self, container):
        """ToolRegistry обрабатывает список inline dict конфигов."""
        tools_config = [
            {
                "tool_id": "inline_calc",
                "code": "async def run(args, state):\n    return args['a'] + args['b']",
                "args_schema": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            },
            {
                "tool_id": "inline_doubler",
                "code": "async def run(args, state):\n    return args['x'] * 2",
                "args_schema": {"x": {"type": "integer"}},
            },
        ]

        tools = await container.tool_registry.create_tools(tools_config)

        assert len(tools) == 2
        assert isinstance(tools[0], CodeTool)
        assert tools[0].name == "inline_calc"
        assert isinstance(tools[1], CodeTool)
        assert tools[1].name == "inline_doubler"

    @pytest.mark.asyncio
    async def test_get_tool_dict_missing_code_raises(self, container):
        """ToolRegistry выбрасывает ошибку если нет code в dict."""
        config = {
            "tool_id": "broken",
            "description": "Без кода",
        }

        with pytest.raises(
            ValueError,
            match=r"Tool 'broken': нет inline code в конфиге и нет шаблона в tool_repository",
        ):
            await container.tool_registry.create_tool(config)


class TestCodeToolSchema:
    """Тесты схемы inline tools."""

    @pytest.mark.asyncio
    async def test_inline_tool_openai_schema(self):
        """CodeTool генерирует корректную OpenAI схему."""
        tool = CodeTool(
            tool_id="greeter",
            code="async def run(args, state):\n    return f\"Hello, {args['name']}!\"",
            description="Приветствует пользователя",
            parameters={
                "name": {"type": "string", "description": "Имя пользователя"},
                "formal": {"type": "boolean", "description": "Формальное приветствие"},
            },
        )

        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "greeter"
        assert schema["function"]["description"] == "Приветствует пользователя"

        params = schema["function"]["parameters"]
        assert "name" in params["properties"]
        assert "formal" in params["properties"]
        assert params["properties"]["name"]["type"] == "string"
        assert params["properties"]["formal"]["type"] == "boolean"

    @pytest.mark.asyncio
    async def test_inline_tool_with_state_access(self):
        """CodeTool имеет доступ к state."""
        tool = CodeTool(
            tool_id="state_reader",
            code="""async def run(args, state):
    user = state.get('user', {})
    return f"User: {user.get('name', 'anonymous')}"
""",
            description="Читает данные пользователя из state",
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="123",
            session_id="test-agent:test-context",
            user={"name": "Alice", "id": 123}
        )
        result = await tool.run({}, state)

        assert result == "User: Alice"


class TestCodeToolsExecution:
    """Тесты выполнения inline tools."""

    @pytest.mark.asyncio
    async def test_inline_tool_with_complex_logic(self):
        """Inline tool с complex логикой."""
        tool = CodeTool(
            tool_id="data_processor",
            code="""async def run(args, state):
    items = args.get('items', [])
    multiplier = args.get('multiplier', 1)

    processed = []
    for item in items:
        if isinstance(item, (int, float)):
            processed.append(item * multiplier)
        else:
            processed.append(item)

    return {
        'processed': processed,
        'count': len(processed),
        'sum': sum(x for x in processed if isinstance(x, (int, float)))
    }
""",
            description="Обрабатывает список элементов",
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run(
            {"items": [1, 2, 3, "skip", 4], "multiplier": 10},
            state,
        )

        assert result["processed"] == [10, 20, 30, "skip", 40]
        assert result["count"] == 5
        assert result["sum"] == 100

    @pytest.mark.asyncio
    async def test_inline_tool_uses_allowed_modules(self):
        """Inline tool может использовать разрешенные модули."""
        tool = CodeTool(
            tool_id="json_tool",
            code="""async def run(args, state):
    import json
    data = {'key': args['value']}
    return json.dumps(data)
""",
            description="Сериализует в JSON",
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({"value": "test"}, state)
        assert result == '{"key": "test"}'

    @pytest.mark.asyncio
    async def test_inline_tool_math_operations(self):
        """Inline tool с math операциями."""
        tool = CodeTool(
            tool_id="math_tool",
            code="""async def run(args, state):
    import math
    return {
        'sqrt': math.sqrt(args['x']),
        'pow': math.pow(args['x'], 2),
        'ceil': math.ceil(args['x'] / 3)
    }
""",
            description="Математические операции",
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({"x": 16}, state)
        assert result["sqrt"] == 4.0
        assert result["pow"] == 256.0
        assert result["ceil"] == 6


class TestCodeToolsInFlowConfig:
    """Тесты inline tools в конфигурации flow."""

    @pytest.mark.asyncio
    async def test_agent_config_with_inline_tools(self, container):
        """Конфигурация агента с inline tools (после прохождения через FlowsLoader)."""
        # После FlowsLoader все tools должны быть inline dict с code
        # Используем уникальные tool_id чтобы не конфликтовать с builtin tools
        agent_tools_config = [
            {
                "tool_id": "test_inline_calc",
                "description": "Калькулятор",
                "args_schema": {"expression": {"type": "string"}},
                "code": "async def run(args, state):\n    return eval(args.get('expression', '0'))",
            },
            {
                "tool_id": "custom_formatter",
                "description": "Форматирует текст",
                "args_schema": {
                    "text": {"type": "string", "description": "Текст"},
                    "uppercase": {"type": "boolean", "description": "В верхнем регистре"},
                },
                "code": """async def run(args, state):
    text = args.get('text', '')
    if args.get('uppercase', False):
        return text.upper()
    return text
""",
            },
        ]

        tools = await container.tool_registry.create_tools(agent_tools_config)

        assert len(tools) == 2

        # Проверяем inline tools
        assert isinstance(tools[0], CodeTool)
        assert isinstance(tools[1], CodeTool)

        formatter = tools[1]
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await formatter.run({"text": "hello", "uppercase": True}, state)
        assert result == "HELLO"

    @pytest.mark.asyncio
    async def test_multiple_inline_tools(self, container):
        """Несколько inline tools в одном агенте."""
        tools_config = [
            {
                "tool_id": "tool_a",
                "code": "async def run(args, state):\n    return 'A'",
            },
            {
                "tool_id": "tool_b",
                "code": "async def run(args, state):\n    return 'B'",
            },
            {
                "tool_id": "tool_c",
                "code": "async def run(args, state):\n    return 'C'",
            },
        ]

        tools = await container.tool_registry.create_tools(tools_config)

        assert len(tools) == 3
        assert all(isinstance(t, CodeTool) for t in tools)

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        results = [await t.run({}, state) for t in tools]
        assert results == ["A", "B", "C"]

