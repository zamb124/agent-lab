"""Инвариант: prepare и process_task используют один и тот же stream task_id."""

from apps.flows.src.channels.base import effective_stream_task_id_for_session
from apps.flows.src.state.execution_state import ExecutionState
from apps.flows.src.state.interrupt import (
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
    assert effective_stream_task_id_for_session("tid-a", None) == "tid-a"


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
    """Plain A2A resume pins stream to interrupt.system.task_id."""
    s = _state_with_interrupt("from-interrupt")
    assert effective_stream_task_id_for_session("from-client", s) == "from-interrupt"


def test_effective_ignores_empty_system_task_id() -> None:
    s = _state_with_interrupt("")
    assert effective_stream_task_id_for_session("from-client", s) == "from-client"


def test_effective_uses_saved_task_id_when_params_empty() -> None:
    s = ExecutionState.create(
        task_id="saved-task",
        context_id="ctx1",
        user_id="user_1",
        session_id="myflow:ctx1",
        content="x",
    )
    assert effective_stream_task_id_for_session("", s) == "saved-task"


def test_ui_action_shares_task_id_with_text_turns() -> None:
    """
    Ui-action и текстовый ход идут одной дорогой: при припаркованном interrupt
    ход продолжает Task из interrupt, а не заводит собственный task_id.
    """
    s = _state_with_interrupt("from-interrupt")
    assert effective_stream_task_id_for_session("ui-action-requested", s) == "from-interrupt"
