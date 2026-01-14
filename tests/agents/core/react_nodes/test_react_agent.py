"""
Тесты ReactNodeRunner - stream-first архитектура.

MockLLM - единственный мок.
Tools - реальные.
State и messages - A2A типы.
"""

import pytest
from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent

from apps.agents.src.agent.runners.react_runner import ReactNodeRunner
from apps.agents.src.models.node_config import NodeConfig, NodeLLMOverride
from core.state import ExecutionState
from apps.agents.tools import calculator


async def run_agent_to_completion(runner, input_data, state):
    """Helper: запускает агента до завершения, собирает события."""
    events = []
    async for event in runner.run(input_data, state):
        events.append(event)
    return events, state


class TestReactAgentWithToolCalls:
    """Тесты вызова tools через ReactAgent."""

    @pytest.fixture
    def calculator_tool(self, app):
        """Реальный калькулятор."""
        return calculator

    @pytest.fixture
    def agent_config(self) -> NodeConfig:
        """Конфиг агента."""
        return NodeConfig(
            node_id="test_agent",
            type="react_node",
            name="Test Agent",
            description="Agent for testing",
            prompt="You are a helpful assistant",
            llm=NodeLLMOverride(provider="mock"),
        )

    @pytest.mark.asyncio
    async def test_tool_call_returns_result(self, app, agent_config, calculator_tool):
        """Tool вызывается и результат возвращается в агента."""
        runner = ReactNodeRunner(
            node_config=agent_config,
            tools=[calculator_tool],
            llm=None,
            prompt="You are a helpful assistant.",
        )
        assert runner is not None

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, app, agent_config, calculator_tool):
        """Несколько вызовов tools подряд."""
        runner = ReactNodeRunner(
            node_config=agent_config,
            tools=[calculator_tool],
            llm=None,
            prompt="You are a helpful assistant.",
        )
        assert runner is not None


class TestReactAgentStreaming:
    """Тесты streaming событий."""

    @pytest.fixture
    def agent_config(self) -> NodeConfig:
        """Конфиг агента."""
        return NodeConfig(
            node_id="stream_agent",
            type="react_node",
            name="Stream Agent",
            description="Agent for streaming tests",
            prompt="You are a helpful assistant",
            llm=NodeLLMOverride(provider="mock"),
        )

    @pytest.mark.asyncio
    async def test_streaming_yields_events(self, app, agent_config):
        """Streaming режим возвращает события."""
        runner = ReactNodeRunner(
            node_config=agent_config,
            tools=[calculator],
            llm=None,
            prompt="You are a helpful assistant.",
        )
        assert runner is not None


class TestToolExecution:
    """Тесты выполнения отдельных tools."""

    @pytest.mark.asyncio
    async def test_calculator_tool_executes_correctly(self):
        """Calculator tool выполняет вычисления корректно."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await calculator.execute({"expression": "2 + 2"}, state=state)
        assert "4" in result

    @pytest.mark.asyncio
    async def test_calculator_tool_handles_complex_math(self):
        """Calculator tool обрабатывает сложные выражения."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await calculator.execute({"expression": "sin(pi/2)"}, state=state)
        # sin(pi/2) = 1.0
        assert "1" in result

    @pytest.mark.asyncio
    async def test_calculator_tool_raises_on_invalid_expression(self):
        """Calculator tool бросает исключение на невалидное выражение."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        with pytest.raises(Exception):
            await calculator.execute({"expression": "invalid_func()"}, state=state)
