"""
Тесты input_mapping для FlowNode.

FlowNode поддерживает input_mapping для передачи конкретных полей из state:
{
    "content": "@state:prepared_query",
    "user_name": "@state:user.name",
    "context": "fixed value"
}
"""


import pytest

from apps.flows.src.runtime.nodes import FlowNode
from core.state import ExecutionState


class TestSubflowInputMapping:
    """Тесты input_mapping для FlowNode."""

    def test_resolve_inputs_no_mapping(self):
        """Без маппинга inputs пустой."""
        node = FlowNode(
            node_id="test_subflow",
            config={"flow_id": "child_flow", "input_mapping": None},
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="123",
            session_id="test-agent:test-context",
            content="hello",
            variables={"api_key": "secret"}
        )

        inputs = node._resolve_inputs(state)

        assert inputs == {}

    def test_prepare_state_no_mapping(self):
        """Без маппинга _prepare_state возвращает копию state."""
        node = FlowNode(
            node_id="test_subflow",
            config={"flow_id": "child_flow", "input_mapping": None},
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="123",
            session_id="test-agent:test-context",
            content="hello",
            variables={"api_key": "secret"}
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.content == "hello"
        assert result.user_id == "123"
        assert result.variables == {"api_key": "secret"}

    def test_resolve_inputs_with_state_reference(self):
        """@state:field берёт значение из state."""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "content": "@state:prepared_query",
                    "user_name": "@state:user_name",
                },
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

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "processed query"
        assert inputs["user_name"] == "John"
        assert "extra_field" not in inputs

    def test_resolve_inputs_with_nested_path(self):
        """@state:nested.path берёт вложенное значение."""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "email": "@state:user.profile.email",
                    "name": "@state:user.name",
                },
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

        inputs = node._resolve_inputs(state)

        assert inputs["email"] == "alice@example.com"
        assert inputs["name"] == "Alice"

    def test_resolve_inputs_with_constant(self):
        """Строка без @state: передаётся как константа."""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "mode": "analysis",
                    "version": "v2",
                    "content": "@state:query",
                },
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

        inputs = node._resolve_inputs(state)

        assert inputs["mode"] == "analysis"
        assert inputs["version"] == "v2"
        assert inputs["content"] == "user question"

    def test_resolve_inputs_missing_field_returns_none(self):
        """Отсутствующее поле возвращает None."""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "content": "@state:missing_field",
                },
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            other="data"
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] is None

    def test_resolve_inputs_missing_nested_path_returns_none(self):
        """Отсутствующий вложенный путь возвращает None."""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "value": "@state:a.b.c",
                },
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            a={"x": 1}
        )

        inputs = node._resolve_inputs(state)

        assert inputs["value"] is None

    def test_resolve_inputs_non_string_value_passed_as_is(self):
        """Нестроковые значения передаются как есть."""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "count": 42,
                    "enabled": True,
                    "items": ["a", "b", "c"],
                },
            },
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )

        inputs = node._resolve_inputs(state)

        assert inputs["count"] == 42
        assert inputs["enabled"] is True
        assert inputs["items"] == ["a", "b", "c"]

    def test_prepare_state_applies_inputs(self):
        """_prepare_state применяет inputs к state."""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "content": "@state:query",
                },
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

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.content == "test"
        assert result.variables == {"key": "value"}
        assert result.session_id == "test-agent:test-context"


class TestSubflowInputMappingIntegration:
    """Интеграционные тесты FlowNode с input_mapping."""

    @pytest.mark.asyncio
    async def test_subflow_with_mock_and_input_mapping(self):
        """FlowNode с input_mapping и mock."""
        node = FlowNode(
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "content": "@state:user_query",
                    "context": "test context",
                },
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

        assert result["result"] == "Mocked response"
        assert result["processed"] is True
        assert result["user_query"] == "What is the weather?"
