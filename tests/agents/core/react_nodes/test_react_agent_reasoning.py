"""
Тесты ReactNodeRunner с reason tool.

MockLLM - единственный мок.
Tools - реальные.

Reason tool добавляется при сборке агента (AgentsLoader), а не в runtime.
Тесты проверяют что reason tool корректно работает если он в списке tools.
"""

import pytest
from a2a.types import TaskArtifactUpdateEvent

from apps.agents.src.agent.runners.react_runner import ReactNodeRunner
from apps.agents.src.models import NodeConfig, LLMConfig
from apps.agents.src.models.node_config import NodeLLMOverride
from core.state import ExecutionState
from apps.agents.src.tools.base import ToolType
from apps.agents.tools import calculator, reason


async def run_agent_to_completion(runner, input_data, state):
    """Helper: запускает агента до завершения, собирает события."""
    events = []
    async for event in runner.run(input_data, state):
        events.append(event)
    return events, state


class TestReasonToolInTools:
    """Тесты reason tool в списке tools."""

    @pytest.fixture
    def agent_config_with_reason(self) -> NodeConfig:
        """Конфиг агента с reason tool в списке."""
        return NodeConfig(
            node_id="reasoning_agent",
            type="react_node",
            name="Reasoning Agent",
            description="Agent with reason tool",
            prompt="You are a helpful assistant.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
        )

    @pytest.fixture
    def agent_config_without_reason(self) -> NodeConfig:
        """Конфиг агента без reason tool."""
        return NodeConfig(
            node_id="simple_agent",
            type="react_node",
            name="Simple Agent",
            description="Agent without reasoning",
            prompt="You are a helpful assistant.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
        )

    def test_reason_tool_available_when_added(self, agent_config_with_reason):
        """Reason tool доступен если добавлен в tools."""
        runner = ReactNodeRunner(
            node_config=agent_config_with_reason,
            tools=[reason, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

        tool_names = [t.name for t in runner.tools]
        assert "reason" in tool_names

    def test_reason_tool_not_present_when_not_added(self, agent_config_without_reason):
        """Reason tool отсутствует если не добавлен в tools."""
        runner = ReactNodeRunner(
            node_config=agent_config_without_reason,
            tools=[calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

        tool_names = [t.name for t in runner.tools]
        assert "reason" not in tool_names

    def test_reason_tool_has_correct_type(self, agent_config_with_reason):
        """Reason tool имеет тип REASON."""
        runner = ReactNodeRunner(
            node_config=agent_config_with_reason,
            tools=[reason, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

        reason_tool = next(t for t in runner.tools if t.name == "reason")
        assert reason_tool.tool_type == ToolType.REASON


class TestReasonToolExecution:
    """Тесты выполнения reason tool."""

    @pytest.fixture
    def agent_config(self) -> NodeConfig:
        """Конфиг агента с reason tool."""
        return NodeConfig(
            node_id="reasoning_emitter",
            type="react_node",
            name="Reasoning Emitter",
            prompt="You are a helpful assistant.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
        )

    @pytest.fixture
    def runner(self, agent_config) -> ReactNodeRunner:
        """ReactNodeRunner с reason tool."""
        return ReactNodeRunner(
            node_config=agent_config,
            tools=[reason, calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

    @pytest.mark.asyncio
    async def test_reasoning_saved_to_history(self, runner, mock_llm_with_queue):
        """Reasoning сохраняется в state.reasoning_history."""
        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Пользователь просит посчитать",
                    "analysis": "Нужно вызвать калькулятор",
                    "plan": "Вычислить выражение",
                    "next_action": "Вызову calculator",
                },
            },
            {
                "type": "tool_call",
                "tool": "calculator",
                "args": {"expression": "2 + 2"},
            },
            {"type": "text", "content": "Результат: 4"},
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            messages=[]
        )
        input_data = {"content": "Сколько будет 2+2?"}

        events, state = await run_agent_to_completion(runner, input_data, state)

        assert len(state.reasoning_history) >= 1

        reasoning_entry = state.reasoning_history[0]
        assert reasoning_entry["observation"] == "Пользователь просит посчитать"
        assert reasoning_entry["analysis"] == "Нужно вызвать калькулятор"
        assert reasoning_entry["plan"] == "Вычислить выражение"
        assert reasoning_entry["next_action"] == "Вызову calculator"


class TestAgentWithoutReasonWorks:
    """Тесты что агент без reason tool работает нормально."""

    @pytest.fixture
    def agent_config(self) -> NodeConfig:
        """Обычный конфиг без reason."""
        return NodeConfig(
            node_id="normal_agent",
            type="react_node",
            name="Normal Agent",
            prompt="You are a helpful assistant.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.0),
        )

    @pytest.fixture
    def runner(self, agent_config) -> ReactNodeRunner:
        """Обычный runner."""
        return ReactNodeRunner(
            node_config=agent_config,
            tools=[calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )

    @pytest.mark.asyncio
    async def test_normal_agent_works(self, runner, mock_llm_with_queue):
        """Агент без reason tool работает нормально."""
        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "calculator",
                "args": {"expression": "5 + 5"},
            },
            {"type": "text", "content": "Результат: 10"},
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            messages=[]
        )
        input_data = {"content": "Сколько 5+5?"}

        events, state = await run_agent_to_completion(runner, input_data, state)

        assert state.response == "Результат: 10"
        assert len(state.reasoning_history) == 0

        tool_names = [t.name for t in runner.tools]
        assert "reason" not in tool_names
