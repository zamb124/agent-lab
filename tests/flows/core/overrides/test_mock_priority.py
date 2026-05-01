"""
Строгие тесты для приоритетов Mock.

Проверяем правильный порядок применения mock:
1. Skill mock (высший приоритет)
2. Agent mock
3. Node-level mock
"""

import pytest
from apps.flows.src.models import FlowConfig, Edge, BranchConfig
from apps.flows.src.mock.config import MockConfig
from apps.flows.src.mock.resolver import (
    resolve_mock_config,
    get_mock_for_tool,
    get_mock_for_flow,
    get_mock_for_node,
    get_mock_for_llm,
)
from core.state import ExecutionState


class TestMockConfigMerge:
    """Тесты merge mock конфигураций через resolve_mock_config."""

    def test_empty_skill_mock_uses_flow_mock(self):
        """Если skill mock пуст - используется agent mock."""
        flow_mock = {
            "enabled": True,
            "tools": {"calculator": 42}
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=None)

        assert config.enabled is True
        assert config.tools["calculator"] == 42

    def test_skill_mock_overrides_flow_mock(self):
        """Skill mock переопределяет agent mock."""
        flow_mock = {
            "enabled": False,
            "tools": {"calculator": 42}
        }
        skill_mock = {
            "enabled": True,
            "tools": {"calculator": 100}
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.enabled is True
        assert config.tools["calculator"] == 100

    def test_skill_mock_merges_tools(self):
        """Skill mock мержит tools с agent mock."""
        flow_mock = {
            "enabled": True,
            "tools": {"calculator": 42, "ask_user": "base response"}
        }
        skill_mock = {
            "enabled": True,
            "tools": {"calculator": 100, "new_tool": "new response"}
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.tools["calculator"] == 100  # Override
        assert config.tools["ask_user"] == "base response"  # From base
        assert config.tools["new_tool"] == "new response"  # Added

    def test_skill_mock_merges_nodes(self):
        """Skill mock мержит nodes с agent mock."""
        flow_mock = {
            "enabled": True,
            "nodes": {
                "classifier": {"route": "order"},
                "formatter": {"response": "base"}
            }
        }
        skill_mock = {
            "enabled": True,
            "nodes": {
                "classifier": {"route": "custom", "extra": "data"},
                "new_node": {"response": "new"}
            }
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        # nodes.update мержит на уровне ключей, не deep
        assert config.nodes["classifier"]["route"] == "custom"
        assert config.nodes["classifier"].get("extra") == "data"
        assert config.nodes["formatter"]["response"] == "base"
        assert config.nodes["new_node"]["response"] == "new"

    def test_skill_mock_overrides_llm(self):
        """Skill mock переопределяет llm responses."""
        flow_mock = {
            "enabled": True,
            "llm": [
                {"type": "text", "content": "Agent response"}
            ]
        }
        skill_mock = {
            "enabled": True,
            "llm": [
                {"type": "text", "content": "Skill response 1"},
                {"type": "text", "content": "Skill response 2"}
            ]
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert len(config.llm) == 2
        # llm может быть list[dict] или list[MockLLMResponse]
        first = config.llm[0]
        content = first["content"] if isinstance(first, dict) else first.content
        assert content == "Skill response 1"

    def test_skill_mock_merges_agents(self):
        """Skill mock мержит agents с agent mock."""
        flow_mock = {
            "enabled": True,
            "flows": {
                "subagent1": "agent response 1",
                "subagent2": "agent response 2"
            }
        }
        skill_mock = {
            "enabled": True,
            "flows": {
                "subagent1": "skill response 1",
                "subagent3": "skill response 3"
            }
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.flows["subagent1"] == "skill response 1"
        assert config.flows["subagent2"] == "agent response 2"
        assert config.flows["subagent3"] == "skill response 3"


class TestMockResolverFunctions:
    """Тесты функций резолва mock из state."""

    def test_get_tool_mock_enabled(self):
        """Tool mock из state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {"calculator": 100}
            }
        )

        result = get_mock_for_tool(state, "calculator")

        assert result == 100

    def test_get_tool_mock_not_found(self):
        """Tool mock не найден - возвращает None."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {"calculator": 42}
            }
        )

        result = get_mock_for_tool(state, "unknown_tool")

        assert result is None

    def test_get_node_mock_from_state(self):
        """Node mock берется из state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "nodes": {
                    "classifier": {"route": "order", "processed": True}
                }
            }
        )

        result = get_mock_for_node(state, "classifier")

        assert result["route"] == "order"
        assert result["processed"] is True

    def test_get_flow_mock_from_state(self):
        """Agent mock берется из state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "flows": {"subagent": "mocked response"}
            }
        )

        result = get_mock_for_flow(state, "subagent")

        assert result == "mocked response"

    def test_get_llm_mock_from_state(self):
        """LLM mock берется из state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "llm": [
                    {"type": "text", "content": "response 1"},
                    {"type": "text", "content": "response 2"}
                ]
            }
        )

        result = get_mock_for_llm(state)

        assert len(result) == 2
        assert result[0]["content"] == "response 1"

    def test_disabled_mock_returns_none(self):
        """Если mock disabled - всегда возвращает None."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": False,
                "tools": {"calculator": 42},
                "flows": {"subagent": "response"},
                "nodes": {"classifier": {"route": "order"}},
                "llm": [{"type": "text", "content": "response"}]
            }
        )

        assert get_mock_for_tool(state, "calculator") is None
        assert get_mock_for_flow(state, "subagent") is None
        assert get_mock_for_node(state, "classifier") is None
        assert get_mock_for_llm(state) is None


class TestMockResolvePriority:
    """Тесты приоритета резолва mock."""

    def test_request_mock_highest_priority(self):
        """Request mock имеет высший приоритет."""
        global_mock = {"enabled": False, "tools": {"t1": "global"}}
        flow_mock = {"enabled": True, "tools": {"t1": "flow"}}
        skill_mock = {"enabled": True, "tools": {"t1": "skill"}}
        request_mock = {"enabled": True, "tools": {"t1": "request"}}

        config = resolve_mock_config(
            global_mock=global_mock,
            flow_mock=flow_mock,
            skill_mock=skill_mock,
            request_mock=request_mock
        )

        assert config.tools["t1"] == "request"

    def test_skill_mock_over_flow(self):
        """Skill mock над flow mock."""
        flow_mock = {"enabled": True, "tools": {"t1": "flow"}}
        skill_mock = {"enabled": True, "tools": {"t1": "skill"}}

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.tools["t1"] == "skill"

    def test_flow_mock_over_global(self):
        """Flow mock над global mock."""
        global_mock = {"enabled": True, "tools": {"t1": "global"}}
        flow_mock = {"enabled": True, "tools": {"t1": "flow"}}

        config = resolve_mock_config(global_mock=global_mock, flow_mock=flow_mock)

        assert config.tools["t1"] == "flow"


class TestMockConfigAllLevels:
    """Тесты всех уровней mock конфигурации."""

    def test_all_levels_mock_priority(self):
        """Проверка приоритета всех уровней mock."""
        # Flow level
        flow_mock = {
            "enabled": True,
            "tools": {"tool1": "flow", "tool2": "flow"},
            "flows": {"sub1": "flow"},
            "nodes": {"node1": {"value": "flow"}, "node2": {"value": "flow"}},
            "llm": [{"type": "text", "content": "flow"}]
        }

        # Skill level (higher priority)
        skill_mock = {
            "enabled": True,
            "tools": {"tool1": "skill", "tool3": "skill"},
            "flows": {"sub1": "skill", "sub2": "skill"},
            "nodes": {"node1": {"value": "skill"}},
            "llm": [{"type": "text", "content": "skill"}]
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        # Tools: skill overrides tool1, adds tool3
        assert config.tools["tool1"] == "skill"
        assert config.tools["tool2"] == "flow"
        assert config.tools["tool3"] == "skill"

        # Agents: skill overrides sub1, adds sub2
        assert config.flows["sub1"] == "skill"
        assert config.flows["sub2"] == "skill"

        # Nodes: skill overrides node1 (at key level)
        assert config.nodes["node1"]["value"] == "skill"
        assert config.nodes["node2"]["value"] == "flow"

        # LLM: skill replaces entirely
        assert len(config.llm) == 1
        first = config.llm[0]
        content = first["content"] if isinstance(first, dict) else first.content
        assert content == "skill"

    def test_example_react_test_full_skill(self):
        """Реальный пример: test_full skill из example_react."""
        flow_mock = {
            "enabled": False,
            "tools": {"calculator": 42},
            "flows": {"example_subflow": "Flow mock response"},
            "nodes": {
                "main": {"response": "Flow mock main"}
            }
        }

        skill_mock = {
            "enabled": True,
            "llm": [{"type": "text", "content": "Полностью замоканный ответ"}],
            "tools": {"calculator": 999, "ask_user": "Mock user response"},
            "flows": {"example_subflow": "Mock subflow response"},
            "nodes": {
                "main": {"response": "Mock node response"},
                "direct_subflow": {"response": "Mock direct subflow node response"}
            }
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        # Enabled from skill
        assert config.enabled is True

        # LLM from skill
        assert len(config.llm) == 1
        first = config.llm[0]
        content = first["content"] if isinstance(first, dict) else first.content
        assert content == "Полностью замоканный ответ"

        # Tools merged with skill priority
        assert config.tools["calculator"] == 999
        assert config.tools["ask_user"] == "Mock user response"

        # Agents merged with skill priority
        assert config.flows["example_subflow"] == "Mock subflow response"

        # Nodes merged with skill priority
        assert config.nodes["main"]["response"] == "Mock node response"
        assert config.nodes["direct_subflow"]["response"] == "Mock direct subflow node response"

    def test_example_graph_test_route_order_skill(self):
        """Реальный пример: test_route_order skill из example_graph."""
        flow_mock = {
            "enabled": False,
            "nodes": {
                "classifier": {"route": "order"},
                "order_processor": {"response": "Flow order response"},
                "formatter": {"processed": True}
            }
        }

        skill_mock = {
            "enabled": True,
            "nodes": {
                "classifier": {"route": "order"},
                "order_processor": {"response": "Тестовый заказ ORD-TEST-001 создан"},
                "formatter": {
                    "response": "[ORDER] Тестовый заказ ORD-TEST-001 создан",
                    "processed": True
                }
            }
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.enabled is True
        assert config.nodes["classifier"]["route"] == "order"
        assert "ORD-TEST-001" in config.nodes["order_processor"]["response"]
        assert "[ORDER]" in config.nodes["formatter"]["response"]

