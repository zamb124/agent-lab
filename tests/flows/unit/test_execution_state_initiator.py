"""`ExecutionState.initiator_user_id`: дефолт, сериализация/rehydrate, независимость от actor."""

from __future__ import annotations

from core.state.execution_state import ExecutionState


def test_initiator_user_id_defaults_none():
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="actor1",
        session_id="flow1:c1",
    )
    assert state.initiator_user_id is None
    assert state.user_id == "actor1"


def test_initiator_user_id_roundtrip_and_independent_from_actor():
    state = ExecutionState(
        task_id="t2",
        context_id="c2",
        user_id="flow_employee_flow2",
        initiator_user_id="human_42",
        session_id="flow2:c2",
    )
    assert state.user_id == "flow_employee_flow2"
    assert state.initiator_user_id == "human_42"

    dumped = state.model_dump()
    assert dumped["initiator_user_id"] == "human_42"

    rehydrated = ExecutionState.model_validate(dumped)
    assert rehydrated.initiator_user_id == "human_42"
    assert rehydrated.user_id == "flow_employee_flow2"
