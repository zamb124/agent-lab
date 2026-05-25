"""
Тесты: emit edge_executed при переходах (линейно, параллель, AND-join).
"""

import pytest

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import ResourceNode
from apps.flows.src.streaming import BaseEmitter
from core.state import ExecutionState
from tests.flows.durable_runtime_harness import run_flow, workflow_state


def _pass_node(node_id: str, *, container: FlowRuntimeContainer) -> ResourceNode:
    return ResourceNode(node_id, {"type": "resource"}, container=container)


@pytest.mark.asyncio
async def test_flow_emits_edge_executed_linear(
    container: FlowRuntimeContainer, unique_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """После ноды A одно ребро A->B, одно edge_executed."""
    nodes = {
        "a": _pass_node("a", container=container),
        "b": _pass_node("b", container=container),
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
        container=container,
    )
    state_task = ExecutionState.model_validate(
        {
            **workflow_state(flow_id=flow.flow_id, unique_id=unique_id).model_dump(
                exclude_none=False
            ),
            "task_id": f"t1-{unique_id}",
            "context_id": f"c1-{unique_id}",
            "session_id": f"{flow.flow_id}:c1-{unique_id}",
        },
    )
    calls: list[tuple[int, str, str]] = []

    async def capture(
        _self, edge_index: int, from_node: str, to_node: str
    ) -> None:
        calls.append((edge_index, from_node, to_node))

    monkeypatch.setattr(BaseEmitter, "emit_edge_executed", capture, raising=True)

    await run_flow(container=container, flow=flow, state=state_task)
    ab_idx = 0
    assert (ab_idx, "a", "b") in calls, f"expected a->b activation, got {calls!r}"


@pytest.mark.asyncio
async def test_flow_emits_two_edges_parallel(
    container: FlowRuntimeContainer, unique_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Два безусловных исходящих из одной ноды — два edge_executed."""
    nodes = {
        "a": _pass_node("a", container=container),
        "b": _pass_node("b", container=container),
        "c": _pass_node("c", container=container),
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
        container=container,
    )
    state = ExecutionState.model_validate(
        {
            **workflow_state(flow_id=flow.flow_id, unique_id=unique_id).model_dump(
                exclude_none=False
            ),
            "task_id": f"t2-{unique_id}",
            "context_id": f"c2-{unique_id}",
            "session_id": f"{flow.flow_id}:c2-{unique_id}",
        },
    )
    calls: list[tuple[int, str, str]] = []

    async def capture(
        _self, edge_index: int, from_node: str, to_node: str
    ) -> None:
        calls.append((edge_index, from_node, to_node))

    monkeypatch.setattr(BaseEmitter, "emit_edge_executed", capture, raising=True)
    await run_flow(container=container, flow=flow, state=state)
    ab = (0, "a", "b")
    ac = (1, "a", "c")
    assert ab in calls and ac in calls, f"expected both branches, got {calls!r}"


@pytest.mark.asyncio
async def test_flow_emits_both_edges_on_and_join(
    container: FlowRuntimeContainer, unique_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    0->1, 0->3, 1->2, 2->3; node 3 incoming_policy all — при открытии join два ребра к 3.
    """
    nodes = {
        "0": _pass_node("0", container=container),
        "1": _pass_node("1", container=container),
        "2": _pass_node("2", container=container),
        "3": ResourceNode(
            "3",
            {
                "type": "resource",
                "incoming_policy": "all",
            },
            container=container,
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
        container=container,
    )
    state_task = ExecutionState.model_validate(
        {
            **workflow_state(flow_id=flow.flow_id, unique_id=unique_id).model_dump(
                exclude_none=False
            ),
            "task_id": f"t3-{unique_id}",
            "context_id": f"c3-{unique_id}",
            "session_id": f"{flow.flow_id}:c3-{unique_id}",
        },
    )
    calls: list[tuple[int, str, str]] = []

    async def capture(
        _self, edge_index: int, from_node: str, to_node: str
    ) -> None:
        calls.append((edge_index, from_node, to_node))

    monkeypatch.setattr(BaseEmitter, "emit_edge_executed", capture, raising=True)
    await run_flow(container=container, flow=flow, state=state_task)
    to3_from_0 = [c for c in calls if c[1] == "0" and c[2] == "3"]
    to3_from_2 = [c for c in calls if c[1] == "2" and c[2] == "3"]
    assert len(to3_from_0) == 1, f"0->3 once, {calls!r}"
    assert len(to3_from_2) == 1, f"2->3 once, {calls!r}"
