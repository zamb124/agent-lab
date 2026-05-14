"""
DEPRECATED: ExecutionState перенесен в core.state.

Этот модуль сохранен для обратной совместимости.
Используйте: from core.state import ExecutionState
"""

# Реэкспорт из core.state БЕЗ warning - это нормально для compatibility слоя
from core.state import (
    ExecutionState,
    InterruptData,
    InterruptPathItem,
    NestedStateData,
    NodeCallInfo,
    State,
)

__all__ = [
    "ExecutionState",
    "State",
    "InterruptData",
    "InterruptPathItem",
    "NodeCallInfo",
    "NestedStateData",
]
