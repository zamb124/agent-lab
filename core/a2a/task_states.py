"""Маппинг platform kebab TaskState ↔ A2A protobuf TaskState."""

from __future__ import annotations

from typing import cast

from a2a.types import Message, TaskState, TaskStatus

# Platform wire/internal kebab strings used outside protobuf enums.
PlatformTaskStateName = str
A2ATaskStateValue = TaskState.ValueType

_PLATFORM_TO_A2A: dict[str, A2ATaskStateValue] = {
    "submitted": TaskState.TASK_STATE_SUBMITTED,
    "working": TaskState.TASK_STATE_WORKING,
    "completed": TaskState.TASK_STATE_COMPLETED,
    "failed": TaskState.TASK_STATE_FAILED,
    "canceled": TaskState.TASK_STATE_CANCELED,
    "input-required": TaskState.TASK_STATE_INPUT_REQUIRED,
    "rejected": TaskState.TASK_STATE_REJECTED,
    "auth-required": TaskState.TASK_STATE_AUTH_REQUIRED,
}

_A2A_TO_PLATFORM: dict[A2ATaskStateValue, str] = {
    TaskState.TASK_STATE_SUBMITTED: "submitted",
    TaskState.TASK_STATE_WORKING: "working",
    TaskState.TASK_STATE_COMPLETED: "completed",
    TaskState.TASK_STATE_FAILED: "failed",
    TaskState.TASK_STATE_CANCELED: "canceled",
    TaskState.TASK_STATE_INPUT_REQUIRED: "input-required",
    TaskState.TASK_STATE_REJECTED: "rejected",
    TaskState.TASK_STATE_AUTH_REQUIRED: "auth-required",
}

TERMINAL_A2A_TASK_STATES: frozenset[A2ATaskStateValue] = frozenset(
    {
        TaskState.TASK_STATE_COMPLETED,
        TaskState.TASK_STATE_FAILED,
        TaskState.TASK_STATE_CANCELED,
        TaskState.TASK_STATE_REJECTED,
    }
)

INTERRUPTED_A2A_TASK_STATES: frozenset[A2ATaskStateValue] = frozenset(
    {
        TaskState.TASK_STATE_INPUT_REQUIRED,
        TaskState.TASK_STATE_AUTH_REQUIRED,
    }
)

# Платформенные kebab-состояния открытой (не терминальной) A2A-задачи.
A2A_OPEN_TASK_STATES: frozenset[str] = frozenset({"submitted", "working"})


def platform_task_state_to_a2a(state: PlatformTaskStateName) -> A2ATaskStateValue:
    """Конвертирует platform kebab (`completed`, `input-required`, …) в A2A enum value."""
    if state not in _PLATFORM_TO_A2A:
        raise ValueError(f"Unknown platform task state for A2A wire: {state!r}")
    return _PLATFORM_TO_A2A[state]


def a2a_task_state_to_platform(state: A2ATaskStateValue) -> PlatformTaskStateName:
    """Конвертирует A2A TaskState value в platform kebab string."""
    if state not in _A2A_TO_PLATFORM:
        raise ValueError(f"Unknown A2A TaskState for platform mapping: {state!r}")
    return _A2A_TO_PLATFORM[state]


def wire_task_state_to_platform(state_value: str) -> PlatformTaskStateName:
    """ProtoJSON/wire `TASK_STATE_*` → platform kebab."""
    try:
        enum_value = TaskState.Value(state_value)
    except ValueError as exc:
        raise ValueError(f"Unknown A2A TaskState wire value: {state_value!r}") from exc
    return a2a_task_state_to_platform(enum_value)


def is_terminal_a2a_task_state(state: A2ATaskStateValue) -> bool:
    return state in TERMINAL_A2A_TASK_STATES


def is_interrupted_a2a_task_state(state: A2ATaskStateValue) -> bool:
    return state in INTERRUPTED_A2A_TASK_STATES


def set_task_status_state(status: TaskStatus, state: A2ATaskStateValue) -> None:
    """
    Присваивает `TaskStatus.state`.

    В runtime protobuf принимает int enum value; stubs a2a-sdk типизируют поле
    как wrapper `TaskState`, поэтому нужен cast на границе SDK.
    """
    status.state = cast(TaskState, state)


def make_task_status(
    state: A2ATaskStateValue,
    *,
    message: Message | None = None,
) -> TaskStatus:
    """Создаёт `TaskStatus` с заданным A2A state и опциональным message."""
    status = TaskStatus()
    set_task_status_state(status, state)
    if message is not None:
        status.message.CopyFrom(message)
    return status


__all__ = [
    "PlatformTaskStateName",
    "A2ATaskStateValue",
    "A2A_OPEN_TASK_STATES",
    "TERMINAL_A2A_TASK_STATES",
    "INTERRUPTED_A2A_TASK_STATES",
    "platform_task_state_to_a2a",
    "a2a_task_state_to_platform",
    "wire_task_state_to_platform",
    "is_terminal_a2a_task_state",
    "is_interrupted_a2a_task_state",
    "set_task_status_state",
    "make_task_status",
]
