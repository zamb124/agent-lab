"""
Тесты AND-join (incoming_policy=all) и fan-in между волнами.
"""

import pytest

from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import CodeNode
from core.errors import FlowPrematureCompletionError


def _bump_node_code(node_id: str) -> str:
    return f"""
def execute(args, state):
    h = state.variables.get("hits")
    if h is None:
        h = {{}}
    else:
        h = dict(h)
    h["{node_id}"] = h.get("{node_id}", 0) + 1
    state.variables = {{**state.variables, "hits": h}}
    return {{}}
"""


@pytest.mark.asyncio
async def test_incoming_policy_all_waits_all_predecessors(make_test_state) -> None:
    """
    0 -> 1 -> 2 -> 3 и 0 -> 3: короткая ветка не должна запускать 3 до прихода с 2.
    """
    nodes = {
        "0": CodeNode("0", {"type": "code", "code": _bump_node_code("0")}),
        "1": CodeNode("1", {"type": "code", "code": _bump_node_code("1")}),
        "2": CodeNode("2", {"type": "code", "code": _bump_node_code("2")}),
        "3": CodeNode(
            "3",
            {
                "type": "code",
                "code": _bump_node_code("3"),
                "incoming_policy": "all",
            },
        ),
    }
    flow = Flow(
        flow_id="join_all",
        name="join_all",
        entry="0",
        nodes=nodes,
        edges=[
            {"from": "0", "to": "1"},
            {"from": "0", "to": "3"},
            {"from": "1", "to": "2"},
            {"from": "2", "to": "3"},
            {"from": "3", "to": None},
        ],
    )
    state = make_test_state()
    out = await flow.run(state)
    hits = out.variables.get("hits") or {}
    assert hits.get("3") == 1, f"expected node 3 once, got {hits!r}"


@pytest.mark.asyncio
async def test_incoming_policy_any_allows_double_join_when_waves_split(make_test_state) -> None:
    """Без incoming_policy (any) нода 3 может выполниться дважды при разнесённых волнах."""
    nodes = {
        "0": CodeNode("0", {"type": "code", "code": _bump_node_code("0")}),
        "1": CodeNode("1", {"type": "code", "code": _bump_node_code("1")}),
        "2": CodeNode("2", {"type": "code", "code": _bump_node_code("2")}),
        "3": CodeNode("3", {"type": "code", "code": _bump_node_code("3")}),
    }
    flow = Flow(
        flow_id="join_any",
        name="join_any",
        entry="0",
        nodes=nodes,
        edges=[
            {"from": "0", "to": "1"},
            {"from": "0", "to": "3"},
            {"from": "1", "to": "2"},
            {"from": "2", "to": "3"},
            {"from": "3", "to": None},
        ],
    )
    state = make_test_state()
    out = await flow.run(state)
    n3_calls = len((out.node_history.get("3") or {}).get("calls") or [])
    assert n3_calls == 2, (
        f"expected node 3 executed twice with any policy, node_history calls={n3_calls}"
    )


@pytest.mark.asyncio
async def test_premature_completion_on_incomplete_and_join(make_test_state) -> None:
    """
    Нода join (all) не собрала всех предков, других переходов нет — FlowPrematureCompletionError.
    Предок «2» в графе есть, но с entry недостижим.
    """
    nodes = {
        "0": CodeNode("0", {"type": "code", "code": _bump_node_code("0")}),
        "1": CodeNode("1", {"type": "code", "code": _bump_node_code("1")}),
        "2": CodeNode("2", {"type": "code", "code": _bump_node_code("2")}),
        "3": CodeNode(
            "3",
            {
                "type": "code",
                "code": _bump_node_code("3"),
                "incoming_policy": "all",
            },
        ),
    }
    flow = Flow(
        flow_id="join_stuck",
        name="join_stuck",
        entry="0",
        nodes=nodes,
        edges=[
            {"from": "0", "to": "1"},
            {"from": "0", "to": "3"},
            {"from": "2", "to": "3"},
            {"from": "1", "to": None},
            {"from": "3", "to": None},
        ],
    )
    state = make_test_state()
    with pytest.raises(FlowPrematureCompletionError) as exc_info:
        await flow.run(state)
    assert exc_info.value.payload.get("reason") == "incomplete_and_join"


@pytest.mark.asyncio
async def test_all_conditional_outgoing_false_is_valid_terminal(make_test_state) -> None:
    """Все исходы к нодам условные и ни одно не сработало — допустимое завершение (роутер / skill)."""
    nodes = {
        "0": CodeNode("0", {"type": "code", "code": _bump_node_code("0")}),
        "1": CodeNode("1", {"type": "code", "code": _bump_node_code("1")}),
        "2": CodeNode("2", {"type": "code", "code": _bump_node_code("2")}),
    }
    flow = Flow(
        flow_id="no_route",
        name="no_route",
        entry="0",
        nodes=nodes,
        edges=[
            {"from": "0", "to": "1"},
            {
                "from": "1",
                "to": "2",
                "condition": {
                    "type": "simple",
                    "variable": "variables.route",
                    "operator": "==",
                    "value": "go",
                },
            },
            {"from": "2", "to": None},
        ],
    )
    state = make_test_state(variables={"route": "stop"})
    out = await flow.run(state)
    hits = out.variables.get("hits") or {}
    assert hits.get("0") == 1
    assert hits.get("1") == 1
    assert hits.get("2") is None


def test_join_required_skips_edge_with_contributes_to_join_false() -> None:
    """Ребро с contributes_to_join=false не попадает в AND-множество предков."""
    nodes = {
        "4": CodeNode("4", {"type": "code", "code": _bump_node_code("4")}),
        "5": CodeNode("5", {"type": "code", "code": _bump_node_code("5")}),
        "6": CodeNode("6", {"type": "code", "code": _bump_node_code("6")}),
    }
    flow = Flow(
        flow_id="join_req",
        name="join_req",
        entry="4",
        nodes=nodes,
        edges=[
            {"from": "4", "to": "5"},
            {"from": "6", "to": "5", "contributes_to_join": False},
            {"from": "5", "to": None},
        ],
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
        {"from": "a", "to": "c"},
        {"from": "b", "to": "c"},
        {"from": "c", "to": None},
    ]
    result = await validator.validate(nodes, edges, "a", {}, flow_id="x")
    codes = {e.code for e in result.errors}
    assert "fan_in_without_incoming_policy" in codes
