"""
State модуль - управление состоянием выполнения агентов.

Основные компоненты:
- ExecutionState: типизированная модель состояния
- InterruptData: данные прерывания
- NestedStateData: вложенное состояние субагентов
"""

from core.state.execution_state import (
    ExecutionState,
    InterruptData,
    InterruptPathItem,
    NodeCallInfo,
    NestedStateData,
    PromptHistoryItem,
    State,
)

__all__ = [
    "ExecutionState",
    "State",
    "InterruptData",
    "InterruptPathItem",
    "NodeCallInfo",
    "NestedStateData",
    "PromptHistoryItem",
]

