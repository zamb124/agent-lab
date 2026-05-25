"""
Тесты вычисления условий переходов (edge conditions).

Runtime-контракт строгий: condition бывает либо simple-object, либо durable code-object.
Строковый mini-DSL намеренно запрещен.
"""

from collections.abc import Mapping, Sequence
from typing import cast, override

import pytest
from pydantic import ValidationError

from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import BaseNode, NodeInputs, NodeRunResult
from core.errors import FlowPrematureCompletionError
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, require_json_object


class StatePatchNode(BaseNode):
    """Deterministic test node that exercises the real BaseNode/Flow path."""

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = inputs
        patch = require_json_object(self.config["patch"], "StatePatchNode.patch")
        for key, value in patch.items():
            state[key] = value
        return state


def make_state(**kwargs: object) -> ExecutionState:
    payload: dict[str, object] = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
    }
    payload.update(kwargs)
    return ExecutionState.model_validate(payload)


def simple_condition(variable: str, operator: str, value: JsonValue) -> JsonObject:
    return require_json_object(
        {"type": "simple", "variable": variable, "operator": operator, "value": value},
        "edge.condition",
    )


def patch_node(node_id: str, patch: Mapping[str, JsonValue]) -> StatePatchNode:
    config = require_json_object(
        {"type": "test_state_patch", "patch": dict(patch)},
        f"nodes.{node_id}",
    )
    return StatePatchNode(node_id=node_id, config=config)


def make_flow(
    *,
    nodes: Mapping[str, Mapping[str, JsonValue]],
    edges: Sequence[JsonObject],
) -> Flow:
    runtime_nodes: dict[str, BaseNode] = {
        node_id: patch_node(node_id, patch)
        for node_id, patch in nodes.items()
    }
    return Flow(
        flow_id="test",
        name="Test",
        entry="start",
        nodes=runtime_nodes,
        edges=edges,
    )


@pytest.mark.usefixtures("app")
class TestStrictConditionContract:
    def test_node_config_requires_explicit_type(self) -> None:
        with pytest.raises(ValueError, match="config.type is required"):
            _ = StatePatchNode(node_id="bad", config={"patch": {}})

    @pytest.mark.asyncio
    async def test_string_condition_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _ = await Flow.from_config(
                {
                    "flow_id": "test",
                    "name": "Test",
                    "entry": "start",
                    "nodes": {
                        "start": {"type": "code", "code": "async def run(args, state): return state"},
                        "order": {"type": "code", "code": "async def run(args, state): return state"},
                    },
                    "edges": [
                        {"from_node": "start", "to_node": "order", "condition": "route == 'order'"}
                    ],
                }
            )

    @pytest.mark.asyncio
    async def test_simple_condition_equals_string(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"route": "order"},
                "order": {"result": "order_node"},
            },
            edges=[
                {"from_node": "start", "to_node": "order", "condition": simple_condition("route", "==", "order")}
            ],
        )

        result = await flow.run(make_state())

        assert result.result == "order_node"

    @pytest.mark.asyncio
    async def test_simple_condition_equals_number(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"count": 5},
                "five": {"result": "five"},
            },
            edges=[
                {"from_node": "start", "to_node": "five", "condition": simple_condition("count", "==", 5)}
            ],
        )

        result = await flow.run(make_state())

        assert result.result == "five"

    @pytest.mark.asyncio
    async def test_simple_condition_not_equals(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"status": "ok"},
                "proceed": {"result": "proceeded"},
            },
            edges=[
                {"from_node": "start", "to_node": "proceed", "condition": simple_condition("status", "!=", "error")}
            ],
        )

        result = await flow.run(make_state())

        assert result.result == "proceeded"

    @pytest.mark.asyncio
    async def test_simple_condition_greater_than(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"score": 85},
                "pass": {"result": "passed"},
            },
            edges=[
                {"from_node": "start", "to_node": "pass", "condition": simple_condition("score", ">", 80)}
            ],
        )

        result = await flow.run(make_state())

        assert result.result == "passed"

    @pytest.mark.asyncio
    async def test_simple_condition_nested_field(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"user": {"role": "admin"}},
                "admin": {"result": "admin_access"},
            },
            edges=[
                {"from_node": "start", "to_node": "admin", "condition": simple_condition("user.role", "==", "admin")}
            ],
        )

        result = await flow.run(make_state())

        assert result.result == "admin_access"

    @pytest.mark.asyncio
    async def test_simple_condition_false_no_transition(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"route": "other"},
                "order": {"result": "order_node"},
            },
            edges=[
                {"from_node": "start", "to_node": "order", "condition": simple_condition("route", "==", "order")}
            ],
        )

        with pytest.raises(FlowPrematureCompletionError) as exc_info:
            _ = await flow.run(make_state())
        assert exc_info.value.payload.get("reason") == "no_conditional_match"


@pytest.mark.usefixtures("app")
class TestSimpleObjectConditions:
    @pytest.mark.asyncio
    async def test_simple_less_or_equal(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"count": 2},
                "few": {"result": "few_items"},
            },
            edges=[
                {"from_node": "start", "to_node": "few", "condition": simple_condition("count", "<=", 3)}
            ],
        )

        result = await flow.run(make_state())

        assert result.result == "few_items"

    @pytest.mark.asyncio
    async def test_simple_in_list(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"route": "support"},
                "support": {"result": "support_handler"},
            },
            edges=[
                {
                    "from_node": "start",
                    "to_node": "support",
                    "condition": simple_condition("route", "in", ["support", "billing"]),
                }
            ],
        )

        result = await flow.run(make_state())

        assert result.result == "support_handler"


@pytest.mark.usefixtures("app")
class TestUnconditionalEdges:
    @pytest.mark.asyncio
    async def test_edge_without_condition(self) -> None:
        flow = make_flow(
            nodes={
                "start": {},
                "next": {"result": "next_executed"},
            },
            edges=[{"from_node": "start", "to_node": "next"}],
        )

        result = await flow.run(make_state())

        assert result.result == "next_executed"

    @pytest.mark.asyncio
    async def test_edge_with_null_condition(self) -> None:
        flow = make_flow(
            nodes={
                "start": {},
                "next": {"result": "executed"},
            },
            edges=[{"from_node": "start", "to_node": "next", "condition": None}],
        )

        result = await flow.run(make_state())

        assert result.result == "executed"


@pytest.mark.usefixtures("app")
class TestMultipleEdges:
    @pytest.mark.asyncio
    async def test_all_matching_conditions_run_in_parallel(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"route": "order"},
                "order": {"order_seen": True},
                "audit": {"audit_seen": True},
            },
            edges=[
                {"from_node": "start", "to_node": "order", "condition": simple_condition("route", "==", "order")},
                {"from_node": "start", "to_node": "audit", "condition": simple_condition("route", "!=", "complaint")},
            ],
        )

        result = await flow.run(make_state())

        assert result["order_seen"] is True
        assert result["audit_seen"] is True

    @pytest.mark.asyncio
    async def test_default_edge_without_condition(self) -> None:
        flow = make_flow(
            nodes={
                "start": {"route": "unknown"},
                "known": {"result": "known"},
                "default_handler": {"result": "default"},
            },
            edges=[
                {"from_node": "start", "to_node": "known", "condition": simple_condition("route", "==", "order")},
                {"from_node": "start", "to_node": "default_handler"},
            ],
        )

        result = await flow.run(make_state())

        assert result.result == "default"


def test_simple_condition_helper_returns_json_object() -> None:
    condition = simple_condition("route", "==", "order")
    assert cast(object, condition["type"]) == "simple"
