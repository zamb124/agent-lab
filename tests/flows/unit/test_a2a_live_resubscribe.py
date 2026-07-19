"""Unit: live SubscribeToTask tail predicate (HITL Stream-First)."""

from a2a.types import Task, TaskStatus
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

from apps.flows.src.channels.a2a import _task_needs_live_subscribe_tail


def _task(state: TaskState.ValueType) -> Task:
    return Task(
        id="tsk-1",
        context_id="ctx-1",
        status=TaskStatus(state=state),
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
