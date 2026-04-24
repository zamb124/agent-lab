"""
State модуль - управление состоянием выполнения агентов.

Основные компоненты:
- ExecutionState: типизированная модель состояния
- InterruptData: данные прерывания
- NestedStateData: вложенное состояние субагентов
"""

from core.state.execution_state import (
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
    "TriggerRuntimeSnapshot",
]

