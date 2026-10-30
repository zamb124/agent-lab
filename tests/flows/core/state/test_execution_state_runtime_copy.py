from __future__ import annotations

from core.state import ExecutionState


def test_runtime_copy_preserves_durable_node_context() -> None:
    state = ExecutionState.create(
        task_id="task_1",
        context_id="ctx_1",
        user_id="user_1",
        session_id="flow_a:ctx_1",
        content="hi",
    )
    state.attach_durable_node_context(
        execution_branch_id="branch_1",
        node_schedule_sequence=7,
        superstep_sequence=3,
    )

    copied = state.runtime_copy()

    assert copied.durable_execution_branch_id == "branch_1"
    assert copied.durable_node_schedule_sequence == 7
    assert copied.durable_superstep_sequence == 3
