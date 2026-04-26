"""
State модуль - управление состоянием выполнения агентов.

Основные компоненты:
- ExecutionState: типизированная модель состояния
- InterruptData: данные прерывания
- NestedStateData: вложенное состояние субагентов
"""

from core.state.mutation_policy import (
    FROZEN_STATE_FIELDS,
    USER_TOOL_PARALLEL_STATE_MERGE_FIELDS,
    assert_frozen_fields_unchanged,
    forbid_frozen_update_key,
    guard_setattr_if_user_code,
    is_runtime_state_mutation_allowed,
    should_skip_field_on_user_returned_state_copy,
    snapshot_frozen_fields,
    user_code_state_mutation_guard,
)
from core.state.execution_state import (
    ExecutionExceptionRecord,
    ExecutionState,
    InterruptPathItem,
    NodeCallInfo,
    NestedStateData,
    PromptHistoryItem,
    State,
)
from core.state.trigger_runtime import TriggerRuntimeSnapshot
from core.state.interrupt import (
    HandoffMode,
    InterruptBody,
    InterruptData,
    InterruptKind,
    InterruptSystemContext,
    OAuthInterrupt,
    OperatorTaskInterrupt,
    UserMessageInterrupt,
    interrupt_body_public_question,
    interrupt_to_response_dict,
    parse_interrupt_body_from_external_dict,
)

__all__ = [
    "FROZEN_STATE_FIELDS",
    "USER_TOOL_PARALLEL_STATE_MERGE_FIELDS",
    "assert_frozen_fields_unchanged",
    "forbid_frozen_update_key",
    "guard_setattr_if_user_code",
    "is_runtime_state_mutation_allowed",
    "should_skip_field_on_user_returned_state_copy",
    "snapshot_frozen_fields",
    "user_code_state_mutation_guard",
    "ExecutionState",
    "State",
    "HandoffMode",
    "InterruptData",
    "InterruptBody",
    "InterruptKind",
    "InterruptSystemContext",
    "UserMessageInterrupt",
    "OperatorTaskInterrupt",
    "OAuthInterrupt",
    "interrupt_body_public_question",
    "interrupt_to_response_dict",
    "parse_interrupt_body_from_external_dict",
    "InterruptPathItem",
    "NodeCallInfo",
    "NestedStateData",
    "PromptHistoryItem",
    "ExecutionExceptionRecord",
    "TriggerRuntimeSnapshot",
]

