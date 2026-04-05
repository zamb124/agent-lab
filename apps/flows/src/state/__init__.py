"""
State модуль - управление состоянием агентов.

Основные модели теперь импортируются из core.state.
Локальные компоненты (StateManager, InterruptManager) остаются здесь.
"""

# Основные модели из core.state (без warning, это нормальный реэкспорт)
from core.state import ExecutionState, State, InterruptData, InterruptPathItem

# Локальные компоненты
from .interrupt_manager import InterruptManager
from .persistence import (
    StateManager,
    create_initial_state,
)
from .node_files import collect_flow_node_files, validate_node_files_list

__all__ = [
    # Модели (из core.state)
    "ExecutionState",
    "State",
    "InterruptData",
    "InterruptPathItem",
    # Persistence (локально)
    "StateManager",
    "create_initial_state",
    # Interrupt (локально)
    "InterruptManager",
    "collect_flow_node_files",
    "validate_node_files_list",
]
