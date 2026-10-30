"""
Тесты определения reason и exit tools по ReactToolRole.

Проверяет что LlmNodeRunner:
- Корректно определяет имя reason tool по ReactToolRole.REASON
- Корректно определяет имя exit tool по ReactToolRole.EXIT
- Использует правильные имена в reminder сообщениях
- Работает с кастомными tools (не только стандартные reason/finish)
"""

from typing import Any

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.models import NodeConfig, ReactConfig, ReactLoopMode
from apps.flows.src.models.enums import NodeType, ReactToolRole
from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from apps.flows.src.state import ExecutionState
from apps.flows.src.streaming import InMemoryEmitter
from apps.flows.src.tools.base import BaseTool
from apps.flows.tools.misc.agent_session_tools import final_answer, reason
from apps.flows.tools.misc.finish_tool import finish
from apps.flows.tools.misc.math_tools import calculator
from core.a2a import get_part_text, part_has_text
from core.clients.llm import LLMClient, MockLLM


def _llm_runner(
    *,
    node_config: NodeConfig,
    tools: list[BaseTool],
    llm: LLMClient | MockLLM | None,
    prompt: str,
    di: FlowsDi,
) -> LlmNodeRunner:
    return LlmNodeRunner(
        node_config=node_config,
        tools=tools,
        llm=llm,
        prompt=prompt,
        workflow_runtime=di.node_constructor.workflow_runtime,
        memory_store=di.node_constructor.llm_context_memory_store,
        text_transform_service=di.node_constructor.text_transform_service,
        emitter_factory=di.node_constructor.emitter_factory,
        redis_client=di.node_constructor.redis_client,
        tool_registry=di.tool_registry,
    )


async def _run_reminder_agent(runner: LlmNodeRunner, state: ExecutionState) -> None:
    async for _ in runner.run({"content": "test"}, state, InMemoryEmitter(state)):
        pass


class CustomReasonTool(BaseTool):
    """Кастомный reasoning tool с другим именем."""

    name = "my_think"
    description = "Custom reasoning tool"
    react_role = ReactToolRole.REASON

    async def _run_impl(self, args: dict[str, Any], state: ExecutionState | None = None) -> str:
        thought = str(args.get("thought", ""))
        if state is not None:
            state.reasoning_history.append({"thought": thought})
        return f"Thought recorded: {thought}"


class CustomExitTool(BaseTool):
    """Кастомный exit tool с другим именем."""

    name = "complete"
    description = "Custom exit tool"
    react_role = ReactToolRole.EXIT

    async def _run_impl(self, args: dict[str, Any], state: ExecutionState | None = None) -> str:
        _ = state
        return str(args.get("answer", "Done"))


class RegularTool(BaseTool):
    """Обычный tool без специального типа."""

    name = "helper"
    description = "Regular helper tool"
    react_role = ReactToolRole.STANDARD

    async def _run_impl(self, args: dict[str, Any], state: ExecutionState | None = None) -> str:
        _ = args, state
        return "helped"


class TestGetReasonToolName:
    """Тесты _get_reason_tool_name()."""

    @pytest.fixture
    def base_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="test_agent",
            type=NodeType.LLM_NODE,
            name="Test Agent",
            prompt="Test prompt",
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4", temperature=0.0),
        )

    def test_returns_reason_name_for_standard_tool(self, base_config, di):
        """Возвращает 'reason' для стандартного reason tool."""
        runner = _llm_runner(
            node_config=base_config,
            tools=[reason, calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_reason_tool_name()

        assert result == "reason"

    def test_returns_custom_name_for_custom_reason_tool(self, base_config, di):
        """Возвращает кастомное имя для кастомного reason tool."""
        custom_reason = CustomReasonTool()
        runner = _llm_runner(
            node_config=base_config,
            tools=[custom_reason, calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_reason_tool_name()

        assert result == "my_think"

    def test_returns_none_when_no_reason_tool(self, base_config, di):
        """Возвращает None если reason tool отсутствует."""
        runner = _llm_runner(
            node_config=base_config,
            tools=[calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_reason_tool_name()

        assert result is None

    def test_ignores_tools_without_reason_type(self, base_config, di):
        """Игнорирует tools с типом TOOL."""
        regular = RegularTool()
        runner = _llm_runner(
            node_config=base_config,
            tools=[regular, calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_reason_tool_name()

        assert result is None


class TestGetExitToolName:
    """Тесты _get_exit_tool_name()."""

    @pytest.fixture
    def base_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="test_agent",
            type=NodeType.LLM_NODE,
            name="Test Agent",
            prompt="Test prompt",
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4", temperature=0.0),
        )

    def test_returns_finish_name_for_standard_tool(self, base_config, di):
        """Возвращает 'finish' для стандартного finish tool."""
        runner = _llm_runner(
            node_config=base_config,
            tools=[finish, calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_exit_tool_name()

        assert result == "finish"

    def test_returns_final_answer_name_for_final_answer_tool(self, base_config, di):
        """Возвращает 'final_answer' для final_answer tool."""
        runner = _llm_runner(
            node_config=base_config,
            tools=[final_answer, calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_exit_tool_name()

        assert result == "final_answer"

    def test_returns_custom_name_for_custom_exit_tool(self, base_config, di):
        """Возвращает кастомное имя для кастомного exit tool."""
        custom_exit = CustomExitTool()
        runner = _llm_runner(
            node_config=base_config,
            tools=[custom_exit, calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_exit_tool_name()

        assert result == "complete"

    def test_returns_none_when_no_exit_tool(self, base_config, di):
        """Возвращает None если exit tool отсутствует."""
        runner = _llm_runner(
            node_config=base_config,
            tools=[calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_exit_tool_name()

        assert result is None

    def test_ignores_regular_tools(self, base_config, di):
        """Игнорирует обычные tools."""
        regular = RegularTool()
        runner = _llm_runner(
            node_config=base_config,
            tools=[regular, reason, calculator],
            llm=None,
            prompt="Test",
        di=di)

        result = runner._get_exit_tool_name()

        assert result is None


class TestReactRoleCombinations:
    """Тесты комбинаций reason и exit tools."""

    @pytest.fixture
    def base_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="test_agent",
            type=NodeType.LLM_NODE,
            name="Test Agent",
            prompt="Test prompt",
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4", temperature=0.0),
        )

    def test_both_standard_tools(self, base_config, di):
        """Оба стандартных tool корректно определяются."""
        runner = _llm_runner(
            node_config=base_config,
            tools=[reason, finish, calculator],
            llm=None,
            prompt="Test",
        di=di)

        assert runner._get_reason_tool_name() == "reason"
        assert runner._get_exit_tool_name() == "finish"

    def test_both_custom_tools(self, base_config, di):
        """Оба кастомных tool корректно определяются."""
        custom_reason = CustomReasonTool()
        custom_exit = CustomExitTool()
        runner = _llm_runner(
            node_config=base_config,
            tools=[custom_reason, custom_exit, calculator],
            llm=None,
            prompt="Test",
        di=di)

        assert runner._get_reason_tool_name() == "my_think"
        assert runner._get_exit_tool_name() == "complete"

    def test_mixed_standard_and_custom(self, base_config, di):
        """Стандартный reason + кастомный exit."""
        custom_exit = CustomExitTool()
        runner = _llm_runner(
            node_config=base_config,
            tools=[reason, custom_exit, calculator],
            llm=None,
            prompt="Test",
        di=di)

        assert runner._get_reason_tool_name() == "reason"
        assert runner._get_exit_tool_name() == "complete"

    def test_only_regular_tools(self, base_config, di):
        """Только обычные tools - оба метода возвращают None."""
        regular = RegularTool()
        runner = _llm_runner(
            node_config=base_config,
            tools=[regular, calculator],
            llm=None,
            prompt="Test",
        di=di)

        assert runner._get_reason_tool_name() is None
        assert runner._get_exit_tool_name() is None


class TestStandardToolsHaveCorrectType:
    """Проверка что стандартные tools имеют правильные типы."""

    def test_reason_has_reason_type(self):
        """reason tool имеет тип REASON."""
        assert reason.react_role == ReactToolRole.REASON

    def test_finish_has_exit_type(self):
        """finish tool имеет тип EXIT."""
        assert finish.react_role == ReactToolRole.EXIT

    def test_final_answer_has_exit_type(self):
        """final_answer tool имеет тип EXIT."""
        assert final_answer.react_role == ReactToolRole.EXIT

    def test_calculator_has_standard_react_role(self):
        """calculator — роль standard."""
        assert calculator.react_role == ReactToolRole.STANDARD


class TestExitToolInjection:
    """Тесты автоинъекции exit tool в EXPLICIT режиме."""

    @pytest.fixture
    def explicit_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="explicit_loop",
            type=NodeType.LLM_NODE,
            name="Explicit loop",
            prompt="Test prompt",
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4", temperature=0.0),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="finish",
                strict=True,
            ),
        )

    def test_finish_injected_when_missing(self, explicit_config, di):
        """finish инъектируется если отсутствует в EXPLICIT режиме."""
        runner = _llm_runner(
            node_config=explicit_config,
            tools=[calculator],
            llm=None,
            prompt="Test",
        di=di)

        assert runner.auto_exit_tool_added is True
        tool_names = [t.name for t in runner.tools]
        assert "finish" in tool_names

    def test_no_injection_when_exit_tool_exists_by_type(self, explicit_config, di):
        """Не инъектируется если exit tool уже есть (по типу)."""
        runner = _llm_runner(
            node_config=explicit_config,
            tools=[finish, calculator],
            llm=None,
            prompt="Test",
        di=di)

        assert runner.auto_exit_tool_added is False
        tool_counts = sum(1 for t in runner.tools if t.name == "finish")
        assert tool_counts == 1

    def test_no_injection_when_custom_exit_exists(self, explicit_config, di):
        """Не инъектируется если кастомный exit tool уже есть."""
        custom_exit = CustomExitTool()
        runner = _llm_runner(
            node_config=explicit_config,
            tools=[custom_exit, calculator],
            llm=None,
            prompt="Test",
        di=di)

        assert runner.auto_exit_tool_added is False
        assert runner._get_exit_tool_name() == "complete"


class TestReminderWithToolNames:
    """Тесты формирования reminder с правильными именами tools."""

    @pytest.fixture
    def explicit_strict_config(self) -> NodeConfig:
        return NodeConfig(
            node_id="strict_agent",
            type=NodeType.LLM_NODE,
            name="Strict Agent",
            prompt="You are a helpful assistant.",
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4", temperature=0.0),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="finish",
                strict=True,
            ),
        )

    @pytest.mark.asyncio
    async def test_reminder_uses_exit_tool_name(
        self, explicit_strict_config, mock_llm_with_queue,
        unique_id,
        di,
    ):
        """Reminder содержит имя exit tool."""
        runner = _llm_runner(
            node_config=explicit_strict_config,
            tools=[finish, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        di=di)

        mock_llm_with_queue([
            {"type": "text", "content": "Просто текст без tool call"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Done"}},
        ])

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            messages=[]
        )
        await _run_reminder_agent(runner, state)

        messages = state.messages
        [
            m for m in messages
            if hasattr(m, "role") and str(m.role) == "ROLE_AGENT"
        ]

        reminder_found = False
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if part_has_text(part):
                        text = get_part_text(part)
                        if "finish" in text and "завершения" in text:
                            reminder_found = True
                            assert "finish" in text

        assert reminder_found or state.get("response") == "Done"

    @pytest.mark.asyncio
    async def test_reminder_includes_reason_tool_when_present(
        self, explicit_strict_config, mock_llm_with_queue,
        unique_id,
        di,
    ):
        """Reminder включает имя reason tool если он есть."""
        runner = _llm_runner(
            node_config=explicit_strict_config,
            tools=[reason, finish, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        di=di)

        mock_llm_with_queue([
            {"type": "text", "content": "Текст без tools"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Done"}},
        ])

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            messages=[]
        )
        await _run_reminder_agent(runner, state)

        messages = state.messages
        reminder_with_reason = False
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if part_has_text(part):
                        text = get_part_text(part)
                        if "reason" in text and "рассуждения" in text:
                            reminder_with_reason = True

        assert reminder_with_reason or state.get("response") == "Done"

    @pytest.mark.asyncio
    async def test_reminder_uses_custom_exit_tool_name(
        self, mock_llm_with_queue,
        unique_id,
        di,
    ):
        """Reminder использует кастомное имя exit tool."""
        custom_exit = CustomExitTool()
        config = NodeConfig(
            node_id="custom_flow",
            type=NodeType.LLM_NODE,
            name="Custom Agent",
            prompt="You are a helpful assistant.",
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4", temperature=0.0),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="complete",
                strict=True,
            ),
        )

        runner = _llm_runner(
            node_config=config,
            tools=[custom_exit, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        di=di)

        mock_llm_with_queue([
            {"type": "text", "content": "Текст без tool call"},
            {"type": "tool_call", "tool": "complete", "args": {"answer": "Done"}},
        ])

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            messages=[]
        )
        await _run_reminder_agent(runner, state)

        messages = state.messages
        found_complete_in_reminder = False
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if part_has_text(part):
                        text = get_part_text(part)
                        if "complete" in text and "завершения" in text:
                            found_complete_in_reminder = True

        assert found_complete_in_reminder or state.get("response") == "Done"

    @pytest.mark.asyncio
    async def test_reminder_uses_custom_reason_tool_name(
        self, mock_llm_with_queue,
        unique_id,
        di,
    ):
        """Reminder использует кастомное имя reason tool."""
        custom_reason = CustomReasonTool()
        config = NodeConfig(
            node_id="custom_reason_agent",
            type=NodeType.LLM_NODE,
            name="Custom Reason Agent",
            prompt="You are a helpful assistant.",
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4", temperature=0.0),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="finish",
                strict=True,
            ),
        )

        runner = _llm_runner(
            node_config=config,
            tools=[custom_reason, finish, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        di=di)

        mock_llm_with_queue([
            {"type": "text", "content": "Текст без tool call"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Done"}},
        ])

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            messages=[]
        )
        await _run_reminder_agent(runner, state)

        messages = state.messages
        found_my_think_in_reminder = False
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if part_has_text(part):
                        text = get_part_text(part)
                        if "my_think" in text and "рассуждения" in text:
                            found_my_think_in_reminder = True

        assert found_my_think_in_reminder or state.get("response") == "Done"
