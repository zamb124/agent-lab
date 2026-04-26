"""Лимиты wall-clock и AST-запрет очевидных вечных циклов в inline Python."""

import pytest

from apps.flows.src.eval.compiler import PythonCompiler
from apps.flows.src.models.node_config import NodeConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.state.flow_deadline import apply_flow_wall_clock_deadline
from core.errors import SafeEvalError
from core.state import ExecutionState


def test_compiler_rejects_while_true() -> None:
    c = PythonCompiler()
    with pytest.raises(SafeEvalError) as ei:
        c.validate("while True:\n    x = 1\n")
    assert "while" in str(ei.value).lower() or "цикл" in str(ei.value)


def test_compiler_allows_while_variable() -> None:
    c = PythonCompiler()
    c.validate(
        "def run(state):\n"
        "    x = 0\n"
        "    while x < 3:\n"
        "        x += 1\n"
        "    return {}\n"
    )


def test_apply_flow_wall_clock_deadline() -> None:
    s = ExecutionState(
        task_id="t1",
        context_id="ctx1",
        user_id="u1",
        session_id="flow_a:ctx1",
    )
    apply_flow_wall_clock_deadline(s, 120)
    assert s.flow_timeout_effective_seconds == 120
    assert s.flow_deadline_monotonic is not None


def test_node_config_node_timeout_cap() -> None:
    with pytest.raises(ValueError):
        NodeConfig(
            node_id="n1",
            type=NodeType.CODE,
            name="x",
            node_timeout_seconds=5000,
        )


def test_node_config_node_timeout_ok() -> None:
    n = NodeConfig(
        node_id="n1",
        type=NodeType.CODE,
        name="x",
        node_timeout_seconds=300,
    )
    assert n.node_timeout_seconds == 300
