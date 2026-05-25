"""
Тесты: emit edge_executed при переходах (линейно, параллель, AND-join).
"""

import pytest

from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import ResourceNode
from apps.flows.src.streaming import BaseEmitter
from core.state import ExecutionState


def _pass_node(node_id: str) -> ResourceNode:
    return ResourceNode(node_id, {"type": "resource"})


@pytest.mark.asyncio
async def test_flow_emits_edge_executed_linear(
    make_test_state, unique_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    """После ноды A одно ребро A->B, одно edge_executed."""
    nodes = {
        "a": _pass_node("a"),
        "b": _pass_node("b"),
    }
    edges = [
        {"from_node": "a", "to_node": "b"},
        {"from_node": "b", "to_node": None},
    ]
    flow = Flow(
        flow_id=f"linear_{unique_id}",
        name="linear",
        entry="a",
        nodes=nodes,
        edges=edges,
    )
    state = make_test_state()
    state_task = ExecutionState.model_validate(
        {**state.model_dump(exclude_none=False), "task_id": "t1", "context_id": "c1"},
    )
    calls: list[tuple[int, str, str]] = []

    async def capture(
        _self, edge_index: int, from_node: str, to_node: str
    ) -> None:
        calls.append((edge_index, from_node, to_node))

    monkeypatch.setattr(BaseEmitter, "emit_edge_executed", capture, raising=True)

    await flow.run(state_task)
    ab_idx = 0
    assert (ab_idx, "a", "b") in calls, f"expected a->b activation, got {calls!r}"


@pytest.mark.asyncio
async def test_flow_emits_two_edges_parallel(
    make_test_state, unique_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Два безусловных исходящих из одной ноды — два edge_executed."""
    nodes = {
        "a": _pass_node("a"),
        "b": _pass_node("b"),
        "c": _pass_node("c"),
    }
    edges = [
        {"from_node": "a", "to_node": "b"},
        {"from_node": "a", "to_node": "c"},
        {"from_node": "b", "to_node": None},
        {"from_node": "c", "to_node": None},
    ]
    flow = Flow(
        flow_id=f"par_{unique_id}",
        name="par",
        entry="a",
        nodes=nodes,
        edges=edges,
    )
    st = make_test_state()
    state = ExecutionState.model_validate(
        {**st.model_dump(exclude_none=False), "task_id": "t2", "context_id": "c2"},
    )
    calls: list[tuple[int, str, str]] = []

    async def capture(
        _self, edge_index: int, from_node: str, to_node: str
    ) -> None:
        calls.append((edge_index, from_node, to_node))

    monkeypatch.setattr(BaseEmitter, "emit_edge_executed", capture, raising=True)
    await flow.run(state)
    ab = (0, "a", "b")
    ac = (1, "a", "c")
    assert ab in calls and ac in calls, f"expected both branches, got {calls!r}"


@pytest.mark.asyncio
async def test_flow_emits_both_edges_on_and_join(
    make_test_state, unique_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    0->1, 0->3, 1->2, 2->3; node 3 incoming_policy all — при открытии join два ребра к 3.
    """
    nodes = {
        "0": _pass_node("0"),
        "1": _pass_node("1"),
        "2": _pass_node("2"),
        "3": ResourceNode(
            "3",
            {
                "type": "resource",
                "incoming_policy": "all",
            },
        ),
    }
    edges = [
        {"from_node": "0", "to_node": "1"},
        {"from_node": "0", "to_node": "3"},
        {"from_node": "1", "to_node": "2"},
        {"from_node": "2", "to_node": "3"},
        {"from_node": "3", "to_node": None},
    ]
    flow = Flow(
        flow_id=f"join_{unique_id}",
        name="join",
        entry="0",
        nodes=nodes,
        edges=edges,
    )
    state = make_test_state()
    state_task = ExecutionState.model_validate(
        {**state.model_dump(exclude_none=False), "task_id": "t3", "context_id": "c3"},
    )
    calls: list[tuple[int, str, str]] = []

    async def capture(
        _self, edge_index: int, from_node: str, to_node: str
    ) -> None:
        calls.append((edge_index, from_node, to_node))

    monkeypatch.setattr(BaseEmitter, "emit_edge_executed", capture, raising=True)
    await flow.run(state_task)
    to3_from_0 = [c for c in calls if c[1] == "0" and c[2] == "3"]
    to3_from_2 = [c for c in calls if c[1] == "2" and c[2] == "3"]
    assert len(to3_from_0) == 1, f"0->3 once, {calls!r}"
    assert len(to3_from_2) == 1, f"2->3 once, {calls!r}"
