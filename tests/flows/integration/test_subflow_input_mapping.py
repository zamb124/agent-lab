"""
Тесты input_mapping для FlowNode.

FlowNode поддерживает input_mapping для передачи конкретных полей из state:
{
    "content": "@state:prepared_query",
    "user_name": "@state:user.name",
    "context": "fixed value"
}
"""

from apps.flows.di import FlowsDi
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.nodes import FlowNode
from core.state import ExecutionState
from core.types import JsonObject


def flow_node(di: FlowsDi, *, node_id: str, config: JsonObject) -> FlowNode:
    if "type" in config:
        raise ValueError("test flow node config must not override canonical node type")
    return FlowNode(
        node_id=node_id,
        config={"type": NodeType.FLOW.value, **config},
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, tool_registry=di.tool_registry, handoff_orchestrator_service=di.handoff_orchestrator_service,
    )


class TestSubflowInputMapping:
    """Тесты input_mapping для FlowNode."""

    def test_resolve_inputs_no_mapping(self, di: FlowsDi, unique_id):
        """Без маппинга inputs пустой."""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={"flow_id": "child_flow", "input_mapping": None},
        )

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="123",
            session_id=f"test-agent:test-context-{unique_id}",
            content="hello",
            variables={"api_key": "secret"},
        )

        inputs = node._resolve_inputs(state)

        assert inputs == {}

    def test_prepare_state_no_mapping(self, di: FlowsDi, unique_id):
        """Без маппинга _prepare_state возвращает копию state."""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={"flow_id": "child_flow", "input_mapping": None},
        )

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="123",
            session_id=f"test-agent:test-context-{unique_id}",
            content="hello",
            variables={"api_key": "secret"},
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.content == "hello"
        assert result.user_id == "123"
        assert result.variables == {"api_key": "secret"}

    def test_resolve_inputs_with_state_reference(self, di: FlowsDi, unique_id):
        """@state:field берёт значение из state."""
        node = flow_node(
            di,
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
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            content="original content",
            prepared_query="processed query",
            user_name="John",
            extra_field="should not be passed",
            variables={"api_key": "secret"},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] == "processed query"
        assert inputs["user_name"] == "John"
        assert "extra_field" not in inputs

    def test_resolve_inputs_with_nested_path(self, di: FlowsDi, unique_id):
        """@state:nested.path берёт вложенное значение."""
        node = flow_node(
            di,
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
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="1",
            session_id=f"test-agent:test-context-{unique_id}",
            user={
                "name": "Alice",
                "profile": {
                    "email": "alice@example.com",
                    "age": 30,
                },
            },
        )

        inputs = node._resolve_inputs(state)

        assert inputs["email"] == "alice@example.com"
        assert inputs["name"] == "Alice"

    def test_resolve_inputs_with_constant(self, di: FlowsDi, unique_id):
        """Строка без @state: передаётся как константа."""
        node = flow_node(
            di,
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
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            query="user question",
            variables={},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["mode"] == "analysis"
        assert inputs["version"] == "v2"
        assert inputs["content"] == "user question"

    def test_resolve_inputs_missing_field_returns_none(self, di: FlowsDi, unique_id):
        """Отсутствующее поле возвращает None."""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "content": "@state:missing_field",
                },
            },
        )

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            other="data",
        )

        inputs = node._resolve_inputs(state)

        assert inputs["content"] is None

    def test_resolve_inputs_missing_nested_path_returns_none(
        self,
        di: FlowsDi,
        unique_id,
    ):
        """Отсутствующий вложенный путь возвращает None."""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "value": "@state:a.b.c",
                },
            },
        )

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            a={"x": 1},
        )

        inputs = node._resolve_inputs(state)

        assert inputs["value"] is None

    def test_resolve_inputs_non_string_value_passed_as_is(
        self,
        di: FlowsDi,
        unique_id,
    ):
        """Нестроковые значения передаются как есть."""
        node = flow_node(
            di,
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
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
        )

        inputs = node._resolve_inputs(state)

        assert inputs["count"] == 42
        assert inputs["enabled"] is True
        assert inputs["items"] == ["a", "b", "c"]

    def test_prepare_state_applies_inputs(self, di: FlowsDi, unique_id):
        """_prepare_state применяет inputs к state."""
        node = flow_node(
            di,
            node_id="test_subflow",
            config={
                "flow_id": "child_flow",
                "input_mapping": {
                    "content": "@state:query",
                },
            },
        )

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="1",
            query="test",
            user_data="skip",
            variables={"key": "value"},
            session_id=f"test-agent:test-context-{unique_id}",
        )

        inputs = node._resolve_inputs(state)
        result = node._prepare_state(state, inputs)

        assert result.content == "test"
        assert result.variables == {"key": "value"}
        assert result.session_id == f"test-agent:test-context-{unique_id}"
