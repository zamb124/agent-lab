"""Инвариант: prepare и process_task используют один и тот же stream task_id."""

import pytest

from apps.flows.src.channels.base import effective_stream_task_id_for_session
from core.state.execution_state import ExecutionState
from core.state.interrupt import (
    InterruptData,
    InterruptSystemContext,
    UserMessageInterrupt,
)


def _state_with_interrupt(task_id_in_system: str) -> ExecutionState:
    base = ExecutionState.create(
        task_id="client-proposed",
        context_id="ctx1",
        user_id="user_1",
        session_id="myflow:ctx1",
        content="x",
    )
    ir = InterruptData(
        body=UserMessageInterrupt(question="pause"),
        system=InterruptSystemContext(task_id=task_id_in_system, context_id="ctx1"),
    )
    return base.model_copy(update={"interrupt": ir})


def test_effective_returns_params_task_id_when_no_state() -> None:
    assert (
        effective_stream_task_id_for_session("tid-a", None) == "tid-a"
    )


def test_effective_returns_params_task_id_when_no_interrupt() -> None:
    s = ExecutionState.create(
        task_id="t1",
        context_id="ctx1",
        user_id="user_1",
        session_id="myflow:ctx1",
        content="x",
    )
    assert effective_stream_task_id_for_session("tid-a", s) == "tid-a"


def test_effective_prefers_interrupt_system_task_id() -> None:
    s = _state_with_interrupt("from-interrupt")
    assert effective_stream_task_id_for_session("from-client", s) == "from-interrupt"


def test_effective_ignores_empty_system_task_id() -> None:
    s = _state_with_interrupt("")
    assert effective_stream_task_id_for_session("from-client", s) == "from-client"
