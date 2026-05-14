"""
Политика мутации ExecutionState: системные поля недоступны для записи из user/eval-кода.

Новые системные атрибуты ExecutionState добавлять в FROZEN_STATE_FIELDS.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from core.state.execution_state import ExecutionState

from core.errors import FrozenStateFieldError

FROZEN_STATE_FIELDS: frozenset[str] = frozenset(
    {
        "task_id",
        "context_id",
        "user_id",
        "session_id",
        "flow_config_version",
        "branch_id",
        "flow_deadline_monotonic",
        "flow_timeout_effective_seconds",
        "current_nodes",
        "join_arrived_preds",
        "interrupt",
        "interrupt_path",
        "hitl_handoff_correlation_id",
        "node_history",
        "execution_exceptions",
        "prompt_history",
        "reasoning_history",
        "pending_reasoning",
        "breakpoints",
        "breakpoint_hit",
        "breakpoint_state",
        "mock",
        "triggers",
        "scheduled_tasks",
        "nested_states",
        "user_groups",
    }
)

FIELDS_COPY_FROM_USER_RETURNED_STATE: frozenset[str] = frozenset(
    {
        "interrupt",
        "interrupt_path",
        "hitl_handoff_correlation_id",
    }
)

# Поля из FROZEN_STATE_FIELDS, которые user/eval и платформенные reason-тулзы
# могут присваивать (interrupt из code-node; reasoning из inline tool / субагента).
USER_CODE_OVERRIDABLE_FROZEN_FIELDS: frozenset[str] = FIELDS_COPY_FROM_USER_RETURNED_STATE | {
    "reasoning_history",
    "pending_reasoning",
}

# Снимок после user/eval-кода: не сравниваем поля, которые inline-код и тулзы
# вправе выставлять (interrupt), дополнять (reasoning_history) и т.д.
FROZEN_STATE_SNAPSHOT_FIELDS: frozenset[str] = frozenset(
    FROZEN_STATE_FIELDS - USER_CODE_OVERRIDABLE_FROZEN_FIELDS
)

USER_TOOL_PARALLEL_STATE_MERGE_FIELDS: frozenset[str] = frozenset(
    {
        "content",
        "response",
        "result",
        "validation",
        "variables",
        "files",
    }
)

_runtime_mutation_allowed: ContextVar[bool] = ContextVar(
    "execution_state_runtime_mutation_allowed", default=True
)


def is_runtime_state_mutation_allowed() -> bool:
    return _runtime_mutation_allowed.get()


@contextmanager
def user_code_state_mutation_guard() -> Iterator[None]:
    token = _runtime_mutation_allowed.set(False)
    try:
        yield
    finally:
        _runtime_mutation_allowed.reset(token)


def raise_if_frozen_field(name: str, *, reason: str = "assign") -> None:
    if name in FROZEN_STATE_FIELDS:
        raise FrozenStateFieldError(
            field=name,
            reason=reason,
        )


def guard_setattr_if_user_code(name: str) -> None:
    if is_runtime_state_mutation_allowed():
        return
    if name in USER_CODE_OVERRIDABLE_FROZEN_FIELDS:
        return
    raise_if_frozen_field(name, reason="assign")


def forbid_frozen_update_key(key: str, *, reason: str = "update") -> None:
    if key in USER_CODE_OVERRIDABLE_FROZEN_FIELDS:
        return
    if key in FROZEN_STATE_FIELDS:
        raise FrozenStateFieldError(field=key, reason=reason)


def snapshot_frozen_fields(state: ExecutionState) -> dict[str, Any]:
    from core.state.execution_state import ExecutionState as ES

    if not isinstance(state, ES):
        return {}
    out: dict[str, Any] = {}
    for k in FROZEN_STATE_SNAPSHOT_FIELDS:
        out[k] = deepcopy(getattr(state, k, None))
    return out


def assert_frozen_fields_unchanged(state: ExecutionState, snapshot: dict[str, Any]) -> None:
    from core.state.execution_state import ExecutionState as ES

    if not isinstance(state, ES):
        return
    for k, old_val in snapshot.items():
        new_val = getattr(state, k, None)
        if old_val != new_val:
            raise FrozenStateFieldError(
                field=k,
                reason="in_place_mutation",
            )


def should_skip_field_on_user_returned_state_copy(field_name: str) -> bool:
    if field_name not in FROZEN_STATE_FIELDS:
        return False
    return field_name not in FIELDS_COPY_FROM_USER_RETURNED_STATE


__all__ = [
    "FROZEN_STATE_FIELDS",
    "FROZEN_STATE_SNAPSHOT_FIELDS",
    "USER_CODE_OVERRIDABLE_FROZEN_FIELDS",
    "USER_TOOL_PARALLEL_STATE_MERGE_FIELDS",
    "assert_frozen_fields_unchanged",
    "forbid_frozen_update_key",
    "guard_setattr_if_user_code",
    "is_runtime_state_mutation_allowed",
    "should_skip_field_on_user_returned_state_copy",
    "snapshot_frozen_fields",
    "user_code_state_mutation_guard",
]
