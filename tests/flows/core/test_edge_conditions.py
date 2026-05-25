"""
Тесты вычисления условий переходов (edge conditions).

Runtime-контракт строгий: condition бывает либо simple-object, либо durable code-object.
Строковый mini-DSL намеренно запрещен.
"""

from collections.abc import Mapping, Sequence
from typing import cast, override

import pytest
from pydantic import ValidationError

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import BaseNode, NodeInputs, NodeRunResult
from core.errors import FlowPrematureCompletionError
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, require_json_object
from tests.flows.durable_runtime_harness import run_flow


class StatePatchNode(BaseNode):
    """Deterministic test node that exercises the real BaseNode/Flow path."""

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = inputs
        patch = require_json_object(self.config["patch"], "StatePatchNode.patch")
        for key, value in patch.items():
            state[key] = value
        return state


def make_state(flow_id: str, unique_id: str, **kwargs: object) -> ExecutionState:
    context_id = f"context-{unique_id}"
    payload: dict[str, object] = {
        "task_id": f"task-{unique_id}",
        "context_id": context_id,
        "user_id": f"user-{unique_id}",
        "session_id": f"{flow_id}:{context_id}",
    }
    payload.update(kwargs)
    return ExecutionState.model_validate(payload)


def simple_condition(variable: str, operator: str, value: JsonValue) -> JsonObject:
    return require_json_object(
        {"type": "simple", "variable": variable, "operator": operator, "value": value},
        "edge.condition",
    )


def patch_node(
    node_id: str,
    patch: Mapping[str, JsonValue],
    *,
    container: FlowRuntimeContainer,
) -> StatePatchNode:
    config = require_json_object(
        {"type": "test_state_patch", "patch": dict(patch)},
        f"nodes.{node_id}",
    )
    return StatePatchNode(node_id=node_id, config=config, container=container)


def make_flow(
    *,
    nodes: Mapping[str, Mapping[str, JsonValue]],
    edges: Sequence[JsonObject],
    container: FlowRuntimeContainer,
) -> Flow:
    runtime_nodes: dict[str, BaseNode] = {
        node_id: patch_node(node_id, patch, container=container)
        for node_id, patch in nodes.items()
    }
    return Flow(
        flow_id="test",
        name="Test",
        entry="start",
        nodes=runtime_nodes,
        edges=edges,
        container=container,
    )


@pytest.mark.usefixtures("app")
class TestStrictConditionContract:
    def test_node_config_requires_explicit_type(self, container: FlowRuntimeContainer) -> None:
        with pytest.raises(ValueError, match="config.type is required"):
            _ = StatePatchNode(node_id="bad", config={"patch": {}}, container=container)

    @pytest.mark.asyncio
    async def test_string_condition_rejected(self, container: FlowRuntimeContainer) -> None:
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
                },
                container=container,
            )

    @pytest.mark.asyncio
    async def test_simple_condition_equals_string(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {"route": "order"},
                "order": {"result": "order_node"},
            },
            edges=[
                {"from_node": "start", "to_node": "order", "condition": simple_condition("route", "==", "order")}
            ],
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "order_node"

    @pytest.mark.asyncio
    async def test_simple_condition_equals_number(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {"count": 5},
                "five": {"result": "five"},
            },
            edges=[
                {"from_node": "start", "to_node": "five", "condition": simple_condition("count", "==", 5)}
            ],
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "five"

    @pytest.mark.asyncio
    async def test_simple_condition_not_equals(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {"status": "ok"},
                "proceed": {"result": "proceeded"},
            },
            edges=[
                {"from_node": "start", "to_node": "proceed", "condition": simple_condition("status", "!=", "error")}
            ],
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "proceeded"

    @pytest.mark.asyncio
    async def test_simple_condition_greater_than(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {"score": 85},
                "pass": {"result": "passed"},
            },
            edges=[
                {"from_node": "start", "to_node": "pass", "condition": simple_condition("score", ">", 80)}
            ],
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "passed"

    @pytest.mark.asyncio
    async def test_simple_condition_nested_field(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {"user": {"role": "admin"}},
                "admin": {"result": "admin_access"},
            },
            edges=[
                {"from_node": "start", "to_node": "admin", "condition": simple_condition("user.role", "==", "admin")}
            ],
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "admin_access"

    @pytest.mark.asyncio
    async def test_simple_condition_false_no_transition(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {"route": "other"},
                "order": {"result": "order_node"},
            },
            edges=[
                {"from_node": "start", "to_node": "order", "condition": simple_condition("route", "==", "order")}
            ],
            container=container,
        )

        with pytest.raises(FlowPrematureCompletionError) as exc_info:
            _ = await run_flow(
                container=container,
                flow=flow,
                state=make_state(flow.flow_id, unique_id),
            )
        assert exc_info.value.payload.get("reason") == "no_conditional_match"


@pytest.mark.usefixtures("app")
class TestSimpleObjectConditions:
    @pytest.mark.asyncio
    async def test_simple_less_or_equal(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {"count": 2},
                "few": {"result": "few_items"},
            },
            edges=[
                {"from_node": "start", "to_node": "few", "condition": simple_condition("count", "<=", 3)}
            ],
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "few_items"

    @pytest.mark.asyncio
    async def test_simple_in_list(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
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
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "support_handler"


@pytest.mark.usefixtures("app")
class TestUnconditionalEdges:
    @pytest.mark.asyncio
    async def test_edge_without_condition(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {},
                "next": {"result": "next_executed"},
            },
            edges=[{"from_node": "start", "to_node": "next"}],
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "next_executed"

    @pytest.mark.asyncio
    async def test_edge_with_null_condition(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
        flow = make_flow(
            nodes={
                "start": {},
                "next": {"result": "executed"},
            },
            edges=[{"from_node": "start", "to_node": "next", "condition": None}],
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "executed"


@pytest.mark.usefixtures("app")
class TestMultipleEdges:
    @pytest.mark.asyncio
    async def test_all_matching_conditions_run_in_parallel(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
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
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result["order_seen"] is True
        assert result["audit_seen"] is True

    @pytest.mark.asyncio
    async def test_default_edge_without_condition(
        self, container: FlowRuntimeContainer, unique_id: str
    ) -> None:
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
            container=container,
        )

        result = await run_flow(
            container=container,
            flow=flow,
            state=make_state(flow.flow_id, unique_id),
        )

        assert result.result == "default"


def test_simple_condition_helper_returns_json_object() -> None:
    condition = simple_condition("route", "==", "order")
    assert cast(object, condition["type"]) == "simple"
