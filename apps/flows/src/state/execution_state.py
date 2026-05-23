"""
DEPRECATED: ExecutionState перенесен в core.state.

Этот модуль сохранен для обратной совместимости.
Используйте: from core.state import ExecutionState
"""

# Реэкспорт из core.state БЕЗ warning - это нормально для compatibility слоя
from core.state import (
    TERMINAL_TASK_STATES,
    ExecutionState,
    ExecutionTaskState,
    InterruptData,
    InterruptPathItem,
    NestedStateData,
    NodeCallInfo,
    State,
)

__all__ = [
    "ExecutionState",
    "ExecutionTaskState",
    "State",
    "TERMINAL_TASK_STATES",
    "InterruptData",
    "InterruptPathItem",
    "NodeCallInfo",
    "NestedStateData",
]
