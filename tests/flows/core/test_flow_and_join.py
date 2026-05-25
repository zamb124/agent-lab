"""
Тесты AND-join (incoming_policy=all) и fan-in между волнами.
"""

import pytest

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import BaseNode
from core.clients.llm import LLMToolCall
from core.errors import FlowPrematureCompletionError
from tests.flows.durable_runtime_harness import run_flow, workflow_state


class _SetVariableNode(BaseNode):
    async def _run_impl(self, state, inputs):
        state.variables = {**state.variables, self.node_id: "done"}
        return {}


class _InterruptNode(BaseNode):
    async def _run_impl(self, state, inputs):
        raise FlowInterrupt(
            question=f"question from {self.node_id}",
            tool_call=LLMToolCall(id=f"call_{self.node_id}", name=f"ask_{self.node_id}"),
        )


class _BumpNode(BaseNode):
    async def _run_impl(self, state, inputs):
        hits = state.variables.get("hits")
        if hits is None:
            hits = {}
        else:
            hits = dict(hits)
        hits[self.node_id] = hits.get(self.node_id, 0) + 1
        state.variables = {**state.variables, "hits": hits}
        return {}


def _bump_node(
    node_id: str,
    *,
    container: FlowRuntimeContainer,
    incoming_policy: str | None = None,
) -> _BumpNode:
    config = {"type": "test"}
    if incoming_policy is not None:
        config["incoming_policy"] = incoming_policy
    return _BumpNode(node_id, config, container=container)


@pytest.mark.asyncio
async def test_incoming_policy_all_waits_all_predecessors(
    container: FlowRuntimeContainer, unique_id: str
) -> None:
    """
    0 -> 1 -> 2 -> 3 и 0 -> 3: короткая ветка не должна запускать 3 до прихода с 2.
    """
    nodes = {
        "0": _bump_node("0", container=container),
        "1": _bump_node("1", container=container),
        "2": _bump_node("2", container=container),
        "3": _bump_node("3", container=container, incoming_policy="all"),
    }
    flow = Flow(
        flow_id="join_all",
        name="join_all",
        entry="0",
        nodes=nodes,
        edges=[
            {"from_node": "0", "to_node": "1"},
            {"from_node": "0", "to_node": "3"},
            {"from_node": "1", "to_node": "2"},
            {"from_node": "2", "to_node": "3"},
            {"from_node": "3", "to_node": None},
        ],
        container=container,
    )
    state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id)
    out = await run_flow(container=container, flow=flow, state=state)
    hits = out.variables.get("hits") or {}
    assert hits.get("3") == 1, f"expected node 3 once, got {hits!r}"


@pytest.mark.asyncio
async def test_parallel_wave_interrupt_keeps_completed_sibling_state(
    container: FlowRuntimeContainer, unique_id: str
) -> None:
    nodes = {
        "start": _SetVariableNode("start", {"type": "test"}, container=container),
        "left": _SetVariableNode("left", {"type": "test"}, container=container),
        "right": _InterruptNode("right", {"type": "test"}, container=container),
    }
    flow = Flow(
        flow_id="parallel_interrupt",
        name="parallel_interrupt",
        entry="start",
        nodes=nodes,
        edges=[
            {"from_node": "start", "to_node": "left"},
            {"from_node": "start", "to_node": "right"},
            {"from_node": "left", "to_node": None},
            {"from_node": "right", "to_node": None},
        ],
        container=container,
    )

    out = await run_flow(
        container=container,
        flow=flow,
        state=workflow_state(flow_id=flow.flow_id, unique_id=unique_id),
    )

    assert out.variables["left"] == "done"
    assert out.interrupt is not None
    assert out.interrupt.question == "question from right"


@pytest.mark.asyncio
async def test_incoming_policy_any_allows_double_join_when_waves_split(
    container: FlowRuntimeContainer, unique_id: str
) -> None:
    """Без incoming_policy (any) нода 3 может выполниться дважды при разнесённых волнах."""
    nodes = {
        "0": _bump_node("0", container=container),
        "1": _bump_node("1", container=container),
        "2": _bump_node("2", container=container),
        "3": _bump_node("3", container=container),
    }
    flow = Flow(
        flow_id="join_any",
        name="join_any",
        entry="0",
        nodes=nodes,
        edges=[
            {"from_node": "0", "to_node": "1"},
            {"from_node": "0", "to_node": "3"},
            {"from_node": "1", "to_node": "2"},
            {"from_node": "2", "to_node": "3"},
            {"from_node": "3", "to_node": None},
        ],
        container=container,
    )
    state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id)
    out = await run_flow(container=container, flow=flow, state=state)
    n3_calls = len((out.node_history.get("3") or {}).get("calls") or [])
    assert n3_calls == 2, (
        f"expected node 3 executed twice with any policy, node_history calls={n3_calls}"
    )


@pytest.mark.asyncio
async def test_premature_completion_on_incomplete_and_join(
    container: FlowRuntimeContainer, unique_id: str
) -> None:
    """
    Нода join (all) не собрала всех предков, других переходов нет — FlowPrematureCompletionError.
    Предок «2» в графе есть, но с entry недостижим.
    """
    nodes = {
        "0": _bump_node("0", container=container),
        "1": _bump_node("1", container=container),
        "2": _bump_node("2", container=container),
        "3": _bump_node("3", container=container, incoming_policy="all"),
    }
    flow = Flow(
        flow_id="join_stuck",
        name="join_stuck",
        entry="0",
        nodes=nodes,
        edges=[
            {"from_node": "0", "to_node": "1"},
            {"from_node": "0", "to_node": "3"},
            {"from_node": "2", "to_node": "3"},
            {"from_node": "1", "to_node": None},
            {"from_node": "3", "to_node": None},
        ],
        container=container,
    )
    state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id)
    with pytest.raises(FlowPrematureCompletionError) as exc_info:
        await run_flow(container=container, flow=flow, state=state)
    assert exc_info.value.payload.get("reason") == "incomplete_and_join"


@pytest.mark.asyncio
async def test_all_conditional_outgoing_false_raises_no_conditional_match(
    container: FlowRuntimeContainer,
    unique_id: str,
) -> None:
    """Все исходы с to!=null с условием, ни одно не выполнилось — FlowPrematureCompletionError."""
    nodes = {
        "0": _bump_node("0", container=container),
        "1": _bump_node("1", container=container),
        "2": _bump_node("2", container=container),
    }
    flow = Flow(
        flow_id="no_route",
        name="no_route",
        entry="0",
        nodes=nodes,
        edges=[
            {"from_node": "0", "to_node": "1"},
            {
                "from_node": "1",
                "to_node": "2",
                "condition": {
                    "type": "simple",
                    "variable": "variables.route",
                    "operator": "==",
                    "value": "go",
                },
            },
            {"from_node": "2", "to_node": None},
        ],
        container=container,
    )
    state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, variables={"route": "stop"})
    with pytest.raises(FlowPrematureCompletionError) as exc_info:
        await run_flow(container=container, flow=flow, state=state)
    assert exc_info.value.payload.get("reason") == "no_conditional_match"


@pytest.mark.asyncio
async def test_router_with_second_branch_reaches_end(
    container: FlowRuntimeContainer, unique_id: str
) -> None:
    """Покрытие альтернативной ветки: маршрут ведёт в 3, затем END (to: null)."""
    nodes = {
        "0": _bump_node("0", container=container),
        "1": _bump_node("1", container=container),
        "2": _bump_node("2", container=container),
        "3": _bump_node("3", container=container),
    }
    flow = Flow(
        flow_id="router_ok",
        name="router_ok",
        entry="0",
        nodes=nodes,
        edges=[
            {"from_node": "0", "to_node": "1"},
            {
                "from_node": "1",
                "to_node": "2",
                "condition": {
                    "type": "simple",
                    "variable": "variables.route",
                    "operator": "==",
                    "value": "go",
                },
            },
            {
                "from_node": "1",
                "to_node": "3",
                "condition": {
                    "type": "simple",
                    "variable": "variables.route",
                    "operator": "==",
                    "value": "stop",
                },
            },
            {"from_node": "2", "to_node": None},
            {"from_node": "3", "to_node": None},
        ],
        container=container,
    )
    state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, variables={"route": "stop"})
    out = await run_flow(container=container, flow=flow, state=state)
    hits = out.variables.get("hits") or {}
    assert hits.get("0") == 1
    assert hits.get("1") == 1
    assert hits.get("2") is None
    assert hits.get("3") == 1


def test_join_required_skips_edge_with_contributes_to_join_false(
    container: FlowRuntimeContainer,
) -> None:
    """Ребро с contributes_to_join=false не попадает в AND-множество предков."""
    nodes = {
        "4": _bump_node("4", container=container),
        "5": _bump_node("5", container=container),
        "6": _bump_node("6", container=container),
    }
    flow = Flow(
        flow_id="join_req",
        name="join_req",
        entry="4",
        nodes=nodes,
        edges=[
            {"from_node": "4", "to_node": "5"},
            {"from_node": "6", "to_node": "5", "contributes_to_join": False},
            {"from_node": "5", "to_node": None},
        ],
        container=container,
    )
    assert flow._join_required["5"] == frozenset({"4"})


@pytest.mark.asyncio
async def test_flow_validator_warns_fan_in_without_policy() -> None:
    from apps.flows.src.services.flow_validator import FlowValidator

    validator = FlowValidator()
    nodes = {
        "a": {"type": "code", "code": "def execute(a,s): return {}"},
        "b": {"type": "code", "code": "def execute(a,s): return {}"},
        "c": {"type": "code", "code": "def execute(a,s): return {}"},
    }
    edges = [
        {"from_node": "a", "to_node": "c"},
        {"from_node": "b", "to_node": "c"},
        {"from_node": "c", "to_node": None},
    ]
    result = await validator.validate(nodes, edges, "a", {}, flow_id="x")
    codes = {e.code for e in result.errors}
    assert "fan_in_without_incoming_policy" in codes


@pytest.mark.asyncio
async def test_flow_validator_rejects_edge_involving_resource_node() -> None:
    from apps.flows.src.services.flow_validator import FlowValidator

    validator = FlowValidator()
    nodes = {
        "a": {"type": "code", "code": "def execute(a,s): return {}"},
        "r": {"type": "resource", "resources": {}},
    }
    edges = [{"from_node": "a", "to_node": "r"}]
    result = await validator.validate(nodes, edges, "a", {}, flow_id="x")
    codes = {e.code for e in result.errors}
    assert "edge_involves_resource_node" in codes


@pytest.mark.asyncio
async def test_flow_validator_no_exit_ignores_isolated_resource_node() -> None:
    from apps.flows.src.services.flow_validator import FlowValidator

    validator = FlowValidator()
    nodes = {
        "a": {"type": "code", "code": "def execute(a,s): return {}"},
        "r": {"type": "resource"},
    }
    edges = [{"from_node": "a", "to_node": None}]
    result = await validator.validate(nodes, edges, "a", {}, flow_id="x")
    assert not any(e.code == "no_exit" for e in result.errors)
