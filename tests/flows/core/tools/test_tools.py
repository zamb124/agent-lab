"""Тесты для tools."""

from unittest.mock import MagicMock

import pytest

from apps.flows.src.models import ToolReference
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.base import BaseTool
from apps.flows.tools.misc.agent_session_tools import ask_user
from apps.flows.tools.misc.finish_tool import finish
from apps.flows.tools.misc.math_tools import calculator

EMPTY_PARAMETERS_SCHEMA = {"type": "object", "properties": {}, "required": []}


class TestBaseTool:
    """Тесты BaseTool."""

    @pytest.mark.asyncio
    async def test_run_calls_run_impl(self, unique_id):
        """BaseTool.run вызывает каноническую реализацию _run_impl."""

        class ToolWithoutMock(BaseTool):
            name = "tool_without_mock"
            description = "Test"

            async def _run_impl(self, args, state=None):
                return "real_called"

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
        )

        tool_without_mock = ToolWithoutMock()
        result_real = await tool_without_mock.run({}, state)
        assert result_real == "real_called"


class TestCalculatorTool:
    """Тесты calculator tool (FunctionTool)."""

    @pytest.mark.asyncio
    async def test_calculator_works(self, unique_id):
        """Калькулятор вычисляет выражения."""
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
        )
        result = await calculator.run({"expression": "2 + 2"}, state)
        assert "4" in result

    @pytest.mark.asyncio
    async def test_calculator_complex_expression(self, unique_id):
        """Сложные выражения."""
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
        )
        result = await calculator.run({"expression": "sqrt(144) + pow(2, 3)"}, state)
        # sqrt(144) = 12, pow(2,3) = 8, total = 20
        assert "20" in result


class TestAskUserTool:
    """Тесты ask_user tool."""

    @pytest.mark.asyncio
    async def test_ask_user_raises_interrupt(self, unique_id):
        """ask_user всегда кидает FlowInterrupt."""
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
        )
        with pytest.raises(FlowInterrupt) as exc_info:
            await ask_user.run({"question": "Как вас зовут?"}, state)

        assert exc_info.value.question == "Как вас зовут?"

    @pytest.mark.asyncio
    async def test_registry_builtin_ids_use_repository_templates(self, app, di):
        """Builtin ids resolve to registered platform tools unless explicit inline code is supplied."""
        from apps.flows.src.tools.code_tool import CodeTool
        from apps.flows.src.tools.decorator import FunctionTool

        for tool_id in ("ask_user", "calculator"):
            tool = await di.tool_registry.create_tool({"tool_id": tool_id})
            assert isinstance(tool, FunctionTool)
            assert tool.name == tool_id

            legacy_inline = await di.tool_registry.create_tool(
                {
                    "tool_id": tool_id,
                    "code": f"async def {tool_id}(args, state) -> JsonDict:\n"
                    "    return {'wrong': True}\n",
                    "parameters_schema": EMPTY_PARAMETERS_SCHEMA,
                }
            )
            assert isinstance(legacy_inline, CodeTool)
            assert legacy_inline.name == tool_id

    @pytest.mark.asyncio
    async def test_registry_create_tool_from_repository_without_builtin(self, app, unique_id, di):
        """Если tool_id не зарегистрирован как builtin, подтягивается шаблон из tool_repository → CodeTool."""
        from apps.flows.src.tools.code_tool import CodeTool

        tid = f"repo_only_{unique_id}"
        await ToolReference.set(
            ToolReference(
                tool_id=tid,
                code="async def run(args, state):\n    return 'from_repo'",
                parameters_schema=EMPTY_PARAMETERS_SCHEMA,
            )
        )
        tool = await di.tool_registry.create_tool({"tool_id": tid})
        assert isinstance(tool, CodeTool)
        assert tool.name == tid


class TestToolRegistryPolicy:
    """Инварианты процессного ToolRegistry."""

    def test_register_rejects_code_tool(self):
        from apps.flows.src.tools.code_tool import CodeTool
        from apps.flows.src.tools.registry import ToolRegistry

        reg = ToolRegistry(flow_factory=MagicMock())
        ct = CodeTool(
            tool_id="ephemeral",
            code="async def run(args, state):\n    return {}",
            parameters_schema=EMPTY_PARAMETERS_SCHEMA,
        )
        with pytest.raises(ValueError, match="CodeTool"):
            reg.register(ct)


class TestFinishTool:
    """Тесты finish tool."""

    @pytest.mark.asyncio
    async def test_finish_returns_answer(self, unique_id):
        """finish возвращает answer."""
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
        )
        result = await finish.run({"answer": "Готово!"}, state)
        assert result == "Готово!"


class TestToolSchema:
    """Тесты OpenAI схемы."""

    def test_to_openai_schema(self):
        """Генерация OpenAI схемы."""
        schema = calculator.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "calculator"
        assert "expression" in schema["function"]["parameters"]["properties"]
