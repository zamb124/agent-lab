"""
Тесты input_mapping для AgentNode.

AgentNode поддерживает input_mapping для передачи конкретных полей из state:
{
    "content": "@state:prepared_query",
    "user_name": "@state:user.name",
    "context": "fixed value"
}
"""

import pytest
from typing import Any, Dict

from apps.agents.src.agent.nodes import AgentNode
from core.state import ExecutionState


class TestSubflowInputMapping:
    """Тесты input_mapping для AgentNode."""

    def test_build_agent_state_no_mapping(self):
        """Без маппинга передаётся весь state."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping=None,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="123",
            session_id="test-agent:test-context",
            content="hello",
            variables={"api_key": "secret"}
        )

        result = node._build_agent_state(state)

        # Весь state скопирован
        assert result.content == "hello"
        assert result.user_id == "123"
        assert result.variables == {"api_key": "secret"}

    def test_build_agent_state_with_state_reference(self):
        """@state:field берёт значение из state."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping={
                "content": "@state:prepared_query",
                "user_name": "@state:user_name",
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="original content",
            prepared_query="processed query",
            user_name="John",
            extra_field="should not be passed",
            variables={"api_key": "secret"}
        )

        result = node._build_agent_state(state)

        # Маппинг применён
        assert result.content == "processed query"
        assert result.user_name == "John"
        # Служебные поля скопированы
        assert result.variables == {"api_key": "secret"}
        # Немаппированные поля не переданы
        assert not hasattr(result, "extra_field")
        assert not hasattr(result, "prepared_query")

    def test_build_agent_state_with_nested_path(self):
        """@state:nested.path берёт вложенное значение."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping={
                "email": "@state:user.profile.email",
                "name": "@state:user.name",
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="1",
            session_id="test-agent:test-context",
            user={
                "name": "Alice",
                "profile": {
                    "email": "alice@example.com",
                    "age": 30,
                },
            }
        )

        result = node._build_agent_state(state)

        assert result.email == "alice@example.com"
        assert result.name == "Alice"

    def test_build_agent_state_with_constant(self):
        """Строка без @state: передаётся как константа."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping={
                "mode": "analysis",
                "version": "v2",
                "content": "@state:query",
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            query="user question",
            variables={}
        )

        result = node._build_agent_state(state)

        assert result.mode == "analysis"
        assert result.version == "v2"
        assert result.content == "user question"

    def test_build_agent_state_missing_field_returns_none(self):
        """Отсутствующее поле возвращает None."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping={
                "content": "@state:missing_field",
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            other="data"
        )

        result = node._build_agent_state(state)

        assert result.content is None

    def test_build_agent_state_missing_nested_path_returns_none(self):
        """Отсутствующий вложенный путь возвращает None."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping={
                "value": "@state:a.b.c",
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            a={"x": 1}
        )

        result = node._build_agent_state(state)

        assert result.value is None

    def test_build_agent_state_non_string_value_passed_as_is(self):
        """Нестроковые значения передаются как есть."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping={
                "count": 42,
                "enabled": True,
                "items": ["a", "b", "c"],
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )

        result = node._build_agent_state(state)

        assert result.count == 42
        assert result.enabled is True
        assert result.items == ["a", "b", "c"]

    def test_build_agent_state_all_dunder_fields_copied(self):
        """Все служебные поля (__name__) копируются."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping={
                "content": "@state:query",
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="1",
            query="test",
            user_data="skip",
            variables={"key": "value"},
            session_id="test-agent:test-context"
        )

        result = node._build_agent_state(state)

        assert result.content == "test"
        assert result.variables == {"key": "value"}
        assert result.session_id == "test-agent:test-context"
        assert not hasattr(result, "user_data")


class TestSubflowInputMappingIntegration:
    """Интеграционные тесты AgentNode с input_mapping."""

    @pytest.mark.asyncio
    async def test_subflow_with_mock_and_input_mapping(self):
        """AgentNode с input_mapping и mock."""
        node = AgentNode(
            node_id="test_subflow",
            agent_id="child_flow",
            input_mapping={
                "content": "@state:user_query",
                "context": "test context",
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user_query="What is the weather?",
            other_data="should not pass",
            mock={
                "enabled": True,
                "nodes": {
                    "test_subflow": {
                        "result": "Mocked response",
                        "processed": True,
                    }
                }
            }
        )

        result = await node.run(state)

        # Mock данные применены
        assert result["result"] == "Mocked response"
        assert result["processed"] is True
        # Оригинальные данные сохранены
        assert result["user_query"] == "What is the weather?"

