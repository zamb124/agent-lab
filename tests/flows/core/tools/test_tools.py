"""
Тесты для tools.

TESTING=true установлен в conftest.py - tools работают в mock режиме.
"""

import os

import pytest

from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools.base import BaseTool, is_test_mode
from apps.flows.tools import ask_user, calculator, finish
from core.state import ExecutionState


class TestIsTestMode:
    """Тесты для is_test_mode()."""

    def test_is_test_mode_returns_true_in_tests(self):
        """TESTING=true установлен в conftest - должен быть True."""
        assert is_test_mode() is True

    def test_testing_env_is_set(self):
        """Переменная TESTING установлена."""
        assert os.environ.get("TESTING") == "true"


class TestBaseTool:
    """Тесты BaseTool."""

    @pytest.mark.asyncio
    async def test_run_calls_execute_mock_when_overridden(self):
        """В тестах execute_mock вызывается только если переопределён."""

        class ToolWithMock(BaseTool):
            name = "tool_with_mock"
            description = "Test"

            async def _run_impl(self, args, state=None):
                return "real_called"

            async def execute_mock(self, args, state=None):
                return "mock_called"

        class ToolWithoutMock(BaseTool):
            name = "tool_without_mock"
            description = "Test"

            async def _run_impl(self, args, state=None):
                return "real_called"

        tool_with_mock = ToolWithMock()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result_mock = await tool_with_mock.run({}, state)
        assert result_mock == "mock_called"

        tool_without_mock = ToolWithoutMock()
        result_real = await tool_without_mock.run({}, state)
        assert result_real == "real_called"

    @pytest.mark.asyncio
    async def test_execute_mock_returns_mock_response_by_default(self):
        """execute_mock по умолчанию возвращает mock_response."""

        class TestTool(BaseTool):
            name = "test_tool"
            description = "Test"
            mock_response = {"status": "ok", "data": [1, 2, 3]}

            async def _run_impl(self, args, state=None):
                return "real"

        tool = TestTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.execute_mock({}, state)

        assert result == {"status": "ok", "data": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_custom_execute_mock(self):
        """Можно переопределить execute_mock() для сложной логики."""

        class ApiTool(BaseTool):
            name = "api_tool"
            description = "API call"

            async def _run_impl(self, args, state=None):
                return {"status": "real"}

            async def execute_mock(self, args, state=None):
                if args.get("id") == "123":
                    return {"status": "found", "name": "Test User"}
                return {"status": "not_found"}

        tool = ApiTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )

        result1 = await tool.run({"id": "123"}, state)
        assert result1 == {"status": "found", "name": "Test User"}

        result2 = await tool.run({"id": "999"}, state)
        assert result2 == {"status": "not_found"}


class TestCalculatorTool:
    """Тесты calculator tool (FunctionTool)."""

    @pytest.mark.asyncio
    async def test_calculator_works(self):
        """Калькулятор вычисляет выражения."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await calculator.run({"expression": "2 + 2"}, state)
        assert "4" in result

    @pytest.mark.asyncio
    async def test_calculator_complex_expression(self):
        """Сложные выражения."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await calculator.run({"expression": "sqrt(144) + pow(2, 3)"}, state)
        # sqrt(144) = 12, pow(2,3) = 8, total = 20
        assert "20" in result


class TestAskUserTool:
    """Тесты ask_user tool."""

    @pytest.mark.asyncio
    async def test_ask_user_raises_interrupt(self):
        """ask_user всегда кидает FlowInterrupt."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        with pytest.raises(FlowInterrupt) as exc_info:
            await ask_user.run({"question": "Как вас зовут?"}, state)

        assert exc_info.value.question == "Как вас зовут?"

    @pytest.mark.asyncio
    async def test_registry_builtin_precedence_over_repository_template(self, app):
        """Для tool_id с процессным builtin materialize возвращает FunctionTool, не CodeTool из БД."""
        from apps.flows.src.container import get_container
        from apps.flows.src.tools.decorator import FunctionTool

        container = get_container()
        tool = await container.tool_registry.create_tool({"tool_id": "ask_user"})
        assert isinstance(tool, FunctionTool)
        assert tool.name == "ask_user"

    @pytest.mark.asyncio
    async def test_registry_create_tool_from_repository_without_builtin(self, app, unique_id):
        """Если tool_id не зарегистрирован как builtin, подтягивается шаблон из tool_repository → CodeTool."""
        from apps.flows.src.container import get_container
        from apps.flows.src.models import ToolReference
        from apps.flows.src.tools.base import CodeTool

        container = get_container()
        tid = f"repo_only_{unique_id}"
        await container.tool_repository.set(
            ToolReference(
                tool_id=tid,
                code="async def execute(args, state):\n    return 'from_repo'",
            )
        )
        tool = await container.tool_registry.create_tool({"tool_id": tid})
        assert isinstance(tool, CodeTool)
        assert tool.name == tid


class TestToolRegistryPolicy:
    """Инварианты процессного ToolRegistry."""

    def test_register_rejects_code_tool(self):
        from apps.flows.src.tools.base import CodeTool
        from apps.flows.src.tools.registry import ToolRegistry

        reg = ToolRegistry()
        ct = CodeTool(
            tool_id="ephemeral",
            code="async def execute(args, state):\n    return {}",
        )
        with pytest.raises(ValueError, match="CodeTool"):
            reg.register(ct)


class TestFinishTool:
    """Тесты finish tool."""

    @pytest.mark.asyncio
    async def test_finish_returns_answer(self):
        """finish возвращает answer."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
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
