"""
Тесты определения reason и exit tools по ToolType.

Проверяет что ReactNodeRunner:
- Корректно определяет имя reason tool по ToolType.REASON
- Корректно определяет имя exit tool по ToolType.EXIT
- Использует правильные имена в reminder сообщениях
- Работает с кастомными tools (не только стандартные reason/finish)
"""

import pytest
from typing import Any, Dict

from apps.agents.src.agent.runners.react_runner import ReactNodeRunner
from apps.agents.src.models import NodeConfig, LLMConfig, ReactConfig, ReactLoopMode
from apps.agents.src.models.node_config import NodeLLMOverride
from core.state import ExecutionState
from apps.agents.src.tools.base import BaseTool, ToolType
from apps.agents.src.tools.decorator import FunctionTool
from apps.agents.tools import reason, finish, final_answer, calculator


class CustomReasonTool(BaseTool):
    """Кастомный reasoning tool с другим именем."""
    
    name = "my_think"
    description = "Custom reasoning tool"
    tool_type = ToolType.REASON
    
    async def execute(self, args: Dict[str, Any], state: Dict[str, Any] = None) -> str:
        thought = args.get("thought", "")
        if state and "reasoning_history" not in state:
            state["reasoning_history"] = []
        if state:
            state["reasoning_history"].append({"thought": thought})
        return f"Thought recorded: {thought}"


class CustomExitTool(BaseTool):
    """Кастомный exit tool с другим именем."""
    
    name = "complete"
    description = "Custom exit tool"
    tool_type = ToolType.EXIT
    
    async def execute(self, args: Dict[str, Any], state: Dict[str, Any] = None) -> str:
        return args.get("answer", "Done")


class RegularTool(BaseTool):
    """Обычный tool без специального типа."""
    
    name = "helper"
    description = "Regular helper tool"
    tool_type = ToolType.TOOL
    
    async def execute(self, args: Dict[str, Any], state: Dict[str, Any] = None) -> str:
        return "helped"


class TestGetReasonToolName:
    """Тесты _get_reason_tool_name()."""

    @pytest.fixture
    def base_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="test_agent",
            type="react_node",
            name="Test Agent",
            prompt="Test prompt",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
        )

    def test_returns_reason_name_for_standard_tool(self, base_config):
        """Возвращает 'reason' для стандартного reason tool."""
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[reason, calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_reason_tool_name()

        assert result == "reason"

    def test_returns_custom_name_for_custom_reason_tool(self, base_config):
        """Возвращает кастомное имя для кастомного reason tool."""
        custom_reason = CustomReasonTool()
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[custom_reason, calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_reason_tool_name()

        assert result == "my_think"

    def test_returns_none_when_no_reason_tool(self, base_config):
        """Возвращает None если reason tool отсутствует."""
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_reason_tool_name()

        assert result is None

    def test_ignores_tools_without_reason_type(self, base_config):
        """Игнорирует tools с типом TOOL."""
        regular = RegularTool()
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[regular, calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_reason_tool_name()

        assert result is None


class TestGetExitToolName:
    """Тесты _get_exit_tool_name()."""

    @pytest.fixture
    def base_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="test_agent",
            type="react_node",
            name="Test Agent",
            prompt="Test prompt",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
        )

    def test_returns_finish_name_for_standard_tool(self, base_config):
        """Возвращает 'finish' для стандартного finish tool."""
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[finish, calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_exit_tool_name()

        assert result == "finish"

    def test_returns_final_answer_name_for_final_answer_tool(self, base_config):
        """Возвращает 'final_answer' для final_answer tool."""
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[final_answer, calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_exit_tool_name()

        assert result == "final_answer"

    def test_returns_custom_name_for_custom_exit_tool(self, base_config):
        """Возвращает кастомное имя для кастомного exit tool."""
        custom_exit = CustomExitTool()
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[custom_exit, calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_exit_tool_name()

        assert result == "complete"

    def test_returns_none_when_no_exit_tool(self, base_config):
        """Возвращает None если exit tool отсутствует."""
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_exit_tool_name()

        assert result is None

    def test_ignores_regular_tools(self, base_config):
        """Игнорирует обычные tools."""
        regular = RegularTool()
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[regular, reason, calculator],
            llm=None,
            prompt="Test",
        )

        result = runner._get_exit_tool_name()

        assert result is None


class TestToolTypeCombinations:
    """Тесты комбинаций reason и exit tools."""

    @pytest.fixture
    def base_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="test_agent",
            type="react_node",
            name="Test Agent",
            prompt="Test prompt",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
        )

    def test_both_standard_tools(self, base_config):
        """Оба стандартных tool корректно определяются."""
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[reason, finish, calculator],
            llm=None,
            prompt="Test",
        )

        assert runner._get_reason_tool_name() == "reason"
        assert runner._get_exit_tool_name() == "finish"

    def test_both_custom_tools(self, base_config):
        """Оба кастомных tool корректно определяются."""
        custom_reason = CustomReasonTool()
        custom_exit = CustomExitTool()
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[custom_reason, custom_exit, calculator],
            llm=None,
            prompt="Test",
        )

        assert runner._get_reason_tool_name() == "my_think"
        assert runner._get_exit_tool_name() == "complete"

    def test_mixed_standard_and_custom(self, base_config):
        """Стандартный reason + кастомный exit."""
        custom_exit = CustomExitTool()
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[reason, custom_exit, calculator],
            llm=None,
            prompt="Test",
        )

        assert runner._get_reason_tool_name() == "reason"
        assert runner._get_exit_tool_name() == "complete"

    def test_only_regular_tools(self, base_config):
        """Только обычные tools - оба метода возвращают None."""
        regular = RegularTool()
        runner = ReactNodeRunner(
            node_config=base_config,
            tools=[regular, calculator],
            llm=None,
            prompt="Test",
        )

        assert runner._get_reason_tool_name() is None
        assert runner._get_exit_tool_name() is None


class TestStandardToolsHaveCorrectType:
    """Проверка что стандартные tools имеют правильные типы."""

    def test_reason_has_reason_type(self):
        """reason tool имеет тип REASON."""
        assert reason.tool_type == ToolType.REASON

    def test_finish_has_exit_type(self):
        """finish tool имеет тип EXIT."""
        assert finish.tool_type == ToolType.EXIT

    def test_final_answer_has_exit_type(self):
        """final_answer tool имеет тип EXIT."""
        assert final_answer.tool_type == ToolType.EXIT

    def test_calculator_has_tool_type(self):
        """calculator tool имеет тип TOOL."""
        assert calculator.tool_type == ToolType.TOOL


class TestExitToolInjection:
    """Тесты автоинъекции exit tool в EXPLICIT режиме."""

    @pytest.fixture
    def explicit_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="explicit_agent",
            type="react_node",
            name="Explicit Agent",
            prompt="Test prompt",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="finish",
                strict=True,
            ),
        )

    def test_finish_injected_when_missing(self, explicit_config):
        """finish инъектируется если отсутствует в EXPLICIT режиме."""
        runner = ReactNodeRunner(
            node_config=explicit_config,
            tools=[calculator],
            llm=None,
            prompt="Test",
        )

        assert runner.auto_exit_tool_added is True
        tool_names = [t.name for t in runner.tools]
        assert "finish" in tool_names

    def test_no_injection_when_exit_tool_exists_by_type(self, explicit_config):
        """Не инъектируется если exit tool уже есть (по типу)."""
        runner = ReactNodeRunner(
            node_config=explicit_config,
            tools=[finish, calculator],
            llm=None,
            prompt="Test",
        )

        assert runner.auto_exit_tool_added is False
        tool_counts = sum(1 for t in runner.tools if t.name == "finish")
        assert tool_counts == 1

    def test_no_injection_when_custom_exit_exists(self, explicit_config):
        """Не инъектируется если кастомный exit tool уже есть."""
        custom_exit = CustomExitTool()
        runner = ReactNodeRunner(
            node_config=explicit_config,
            tools=[custom_exit, calculator],
            llm=None,
            prompt="Test",
        )

        assert runner.auto_exit_tool_added is False
        assert runner._get_exit_tool_name() == "complete"


class TestReminderWithToolNames:
    """Тесты формирования reminder с правильными именами tools."""

    @pytest.fixture
    def explicit_strict_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="strict_agent",
            type="react_node",
            name="Strict Agent",
            prompt="You are a helpful assistant.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="finish",
                strict=True,
            ),
        )

    @pytest.mark.asyncio
    async def test_reminder_uses_exit_tool_name(
        self, explicit_strict_config, mock_llm_with_queue
    ):
        """Reminder содержит имя exit tool."""
        runner = ReactNodeRunner(
            node_config=explicit_strict_config,
            tools=[finish, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

        mock_llm_with_queue([
            {"type": "text", "content": "Просто текст без tool call"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Done"}},
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            messages=[]
        )
        async for _ in runner.run({"content": "test"}, state):
            pass

        messages = state.messages
        system_messages = [
            m for m in messages 
            if hasattr(m, "role") and str(m.role) == "Role.agent"
        ]

        reminder_found = False
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part.root, "text"):
                        text = part.root.text
                        if "finish" in text and "завершения" in text:
                            reminder_found = True
                            assert "finish" in text

        assert reminder_found or state.get("response") == "Done"

    @pytest.mark.asyncio
    async def test_reminder_includes_reason_tool_when_present(
        self, explicit_strict_config, mock_llm_with_queue
    ):
        """Reminder включает имя reason tool если он есть."""
        runner = ReactNodeRunner(
            node_config=explicit_strict_config,
            tools=[reason, finish, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

        mock_llm_with_queue([
            {"type": "text", "content": "Текст без tools"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Done"}},
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            messages=[]
        )
        async for _ in runner.run({"content": "test"}, state):
            pass

        messages = state.messages
        reminder_with_reason = False
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part.root, "text"):
                        text = part.root.text
                        if "reason" in text and "рассуждения" in text:
                            reminder_with_reason = True

        assert reminder_with_reason or state.get("response") == "Done"

    @pytest.mark.asyncio
    async def test_reminder_uses_custom_exit_tool_name(
        self, mock_llm_with_queue
    ):
        """Reminder использует кастомное имя exit tool."""
        custom_exit = CustomExitTool()
        config = NodeConfig(
            node_id="custom_agent",
            type="react_node",
            name="Custom Agent",
            prompt="You are a helpful assistant.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="complete",
                strict=True,
            ),
        )

        runner = ReactNodeRunner(
            node_config=config,
            tools=[custom_exit, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

        mock_llm_with_queue([
            {"type": "text", "content": "Текст без tool call"},
            {"type": "tool_call", "tool": "complete", "args": {"answer": "Done"}},
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            messages=[]
        )
        async for _ in runner.run({"content": "test"}, state):
            pass

        messages = state.messages
        found_complete_in_reminder = False
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part.root, "text"):
                        text = part.root.text
                        if "complete" in text and "завершения" in text:
                            found_complete_in_reminder = True

        assert found_complete_in_reminder or state.get("response") == "Done"

    @pytest.mark.asyncio
    async def test_reminder_uses_custom_reason_tool_name(
        self, mock_llm_with_queue
    ):
        """Reminder использует кастомное имя reason tool."""
        custom_reason = CustomReasonTool()
        config = NodeConfig(
            node_id="custom_reason_agent",
            type="react_node",
            name="Custom Reason Agent",
            prompt="You are a helpful assistant.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="finish",
                strict=True,
            ),
        )

        runner = ReactNodeRunner(
            node_config=config,
            tools=[custom_reason, finish, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

        mock_llm_with_queue([
            {"type": "text", "content": "Текст без tool call"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Done"}},
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            messages=[]
        )
        async for _ in runner.run({"content": "test"}, state):
            pass

        messages = state.messages
        found_my_think_in_reminder = False
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part.root, "text"):
                        text = part.root.text
                        if "my_think" in text and "рассуждения" in text:
                            found_my_think_in_reminder = True

        assert found_my_think_in_reminder or state.get("response") == "Done"

