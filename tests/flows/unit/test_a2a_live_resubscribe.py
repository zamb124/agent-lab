"""Unit: live SubscribeToTask tail predicate (HITL Stream-First)."""

from a2a.types import Message, Part, Role, Task, TaskStatus
from a2a.types.a2a_pb2 import (
    TASK_STATE_CANCELED,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
    TASK_STATE_INPUT_REQUIRED,
    TASK_STATE_REJECTED,
    TASK_STATE_SUBMITTED,
    TASK_STATE_WORKING,
    TaskState,
)

from apps.flows.src.channels.a2a import (
    _task_needs_live_subscribe_tail,
    _this_send_finished_in_process,
)


def _task(
    state: TaskState.ValueType,
    *,
    history_ids: tuple[str, ...] = (),
    status_message_id: str = "",
) -> Task:
    history = [
        Message(
            message_id=message_id,
            role=Role.ROLE_AGENT,
            parts=[Part(text=message_id)],
        )
        for message_id in history_ids
    ]
    status = TaskStatus(state=state)
    if status_message_id:
        status.message.CopyFrom(
            Message(
                message_id=status_message_id,
                role=Role.ROLE_AGENT,
                parts=[Part(text=status_message_id)],
            )
        )
    return Task(
        id="tsk-1",
        context_id="ctx-1",
        status=status,
        history=history,
    )


def test_live_tail_needed_for_input_required_and_working() -> None:
    assert _task_needs_live_subscribe_tail(_task(TASK_STATE_INPUT_REQUIRED)) is True
    assert _task_needs_live_subscribe_tail(_task(TASK_STATE_WORKING)) is True
    assert _task_needs_live_subscribe_tail(_task(TASK_STATE_SUBMITTED)) is True


def test_live_tail_not_needed_for_terminal() -> None:
    assert _task_needs_live_subscribe_tail(_task(TASK_STATE_COMPLETED)) is False
    assert _task_needs_live_subscribe_tail(_task(TASK_STATE_FAILED)) is False
    assert _task_needs_live_subscribe_tail(_task(TASK_STATE_CANCELED)) is False
    assert _task_needs_live_subscribe_tail(_task(TASK_STATE_REJECTED)) is False


def test_in_process_first_send_returns_parked_projection() -> None:
    assert _this_send_finished_in_process(None, _task(TASK_STATE_COMPLETED)) is True
    assert _this_send_finished_in_process(
        _task(TASK_STATE_WORKING),
        _task(TASK_STATE_INPUT_REQUIRED),
    ) is True


def test_stale_parked_projection_does_not_count_as_this_send() -> None:
    prior = _task(TASK_STATE_COMPLETED, history_ids=("m1",), status_message_id="s1")
    current = _task(TASK_STATE_COMPLETED, history_ids=("m1",), status_message_id="s1")
    assert _this_send_finished_in_process(prior, current) is False


def test_same_task_id_next_turn_counts_when_projection_advanced() -> None:
    prior = _task(TASK_STATE_COMPLETED, history_ids=("m1",), status_message_id="s1")
    current = _task(
        TASK_STATE_COMPLETED,
        history_ids=("m1", "m2"),
        status_message_id="s2",
    )
    assert _this_send_finished_in_process(prior, current) is True


def test_working_projection_never_short_circuits_collect() -> None:
    assert _this_send_finished_in_process(None, _task(TASK_STATE_WORKING)) is False
    assert _this_send_finished_in_process(
        _task(TASK_STATE_COMPLETED, history_ids=("m1",)),
        _task(TASK_STATE_SUBMITTED, history_ids=("m1",)),
    ) is False
