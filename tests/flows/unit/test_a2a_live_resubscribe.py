"""Unit: live tasks/resubscribe tail predicate (HITL Stream-First)."""

from a2a.types import Task, TaskState, TaskStatus

from apps.flows.src.channels.a2a import _task_needs_live_resubscribe_tail


def _task(state: TaskState) -> Task:
    return Task(
        id="tsk-1",
        contextId="ctx-1",
        status=TaskStatus(state=state),
    )


def test_live_tail_needed_for_input_required_and_working() -> None:
    assert _task_needs_live_resubscribe_tail(_task(TaskState.input_required)) is True
    assert _task_needs_live_resubscribe_tail(_task(TaskState.working)) is True
    assert _task_needs_live_resubscribe_tail(_task(TaskState.submitted)) is True


def test_live_tail_not_needed_for_terminal() -> None:
    assert _task_needs_live_resubscribe_tail(_task(TaskState.completed)) is False
    assert _task_needs_live_resubscribe_tail(_task(TaskState.failed)) is False
    assert _task_needs_live_resubscribe_tail(_task(TaskState.canceled)) is False
    assert _task_needs_live_resubscribe_tail(_task(TaskState.rejected)) is False
