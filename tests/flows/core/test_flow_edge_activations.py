"""
Тесты: emit edge_executed при переходах (линейно, параллель, AND-join).
"""

import pytest

from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import CodeNode
from apps.flows.src.streaming import Emitter
from core.state import ExecutionState


def _trivial_code(node_id: str) -> str:
    return f"""
async def execute(args, state):
    return {{"k": "{node_id}"}}
"""


@pytest.mark.asyncio
async def test_flow_emits_edge_executed_linear(
    make_test_state, unique_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    """После ноды A одно ребро A->B, одно edge_executed."""
    nodes = {
        "a": CodeNode("a", {"type": "code", "code": _trivial_code("a")}),
        "b": CodeNode("b", {"type": "code", "code": _trivial_code("b")}),
    }
    edges = [
        {"from": "a", "to": "b"},
        {"from": "b", "to": None},
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

    monkeypatch.setattr(Emitter, "emit_edge_executed", capture, raising=True)

    await flow.run(state_task)
    ab_idx = 0
    assert (ab_idx, "a", "b") in calls, f"expected a->b activation, got {calls!r}"


@pytest.mark.asyncio
async def test_flow_emits_two_edges_parallel(
    make_test_state, unique_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Два безусловных исходящих из одной ноды — два edge_executed."""
    nodes = {
        "a": CodeNode("a", {"type": "code", "code": _trivial_code("a")}),
        "b": CodeNode("b", {"type": "code", "code": _trivial_code("b")}),
        "c": CodeNode("c", {"type": "code", "code": _trivial_code("c")}),
    }
    edges = [
        {"from": "a", "to": "b"},
        {"from": "a", "to": "c"},
        {"from": "b", "to": None},
        {"from": "c", "to": None},
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

    monkeypatch.setattr(Emitter, "emit_edge_executed", capture, raising=True)
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
        "0": CodeNode("0", {"type": "code", "code": _trivial_code("0")}),
        "1": CodeNode("1", {"type": "code", "code": _trivial_code("1")}),
        "2": CodeNode("2", {"type": "code", "code": _trivial_code("2")}),
        "3": CodeNode(
            "3",
            {
                "type": "code",
                "code": _trivial_code("3"),
                "incoming_policy": "all",
            },
        ),
    }
    edges = [
        {"from": "0", "to": "1"},
        {"from": "0", "to": "3"},
        {"from": "1", "to": "2"},
        {"from": "2", "to": "3"},
        {"from": "3", "to": None},
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

    monkeypatch.setattr(Emitter, "emit_edge_executed", capture, raising=True)
    await flow.run(state_task)
    to3_from_0 = [c for c in calls if c[1] == "0" and c[2] == "3"]
    to3_from_2 = [c for c in calls if c[1] == "2" and c[2] == "3"]
    assert len(to3_from_0) == 1, f"0->3 once, {calls!r}"
    assert len(to3_from_2) == 1, f"2->3 once, {calls!r}"


@pytest.mark.asyncio
async def test_flow_emits_edge_error_on_python_condition_failure(
    make_test_state, unique_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Падение check(state) на ребре: emit edge_error, затем исходное исключение."""
    nodes = {
        "a": CodeNode("a", {"type": "code", "code": _trivial_code("a")}),
        "b": CodeNode("b", {"type": "code", "code": _trivial_code("b")}),
    }
    edges = [
        {
            "from": "a",
            "to": "b",
            "condition": {
                "type": "python",
                "code": "def check(state):\n    return 1 / 0\n",
            },
        },
    ]
    flow = Flow(
        flow_id=f"edge_err_{unique_id}",
        name="edge_err",
        entry="a",
        nodes=nodes,
        edges=edges,
    )
    st = make_test_state()
    state = ExecutionState.model_validate(
        {**st.model_dump(exclude_none=False), "task_id": "t_err", "context_id": "c_err"},
    )
    err_calls: list[tuple[int, str, str, str]] = []

    async def capture_error(
        _self,
        edge_index: int,
        from_node: str,
        to_node: str,
        error: str,
    ) -> None:
        err_calls.append((edge_index, from_node, to_node, error))

    monkeypatch.setattr(Emitter, "emit_edge_error", capture_error, raising=True)

    with pytest.raises(ValueError, match="Python-условие ребра"):
        await flow.run(state)

    assert len(err_calls) == 1
    assert err_calls[0][0] == 0
    assert err_calls[0][1] == "a"
    assert err_calls[0][2] == "b"
    assert "division" in err_calls[0][3].lower() or "zero" in err_calls[0][3].lower()
