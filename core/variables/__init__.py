"""
Система работы с переменными для промптов и агентов.
"""

from core.variables.resolver import (
    UnmatchedBracesError,
    VariableResolutionError,
    VariableResolver,
    VarResolver,
    get_state,
    set_state_in_context,
)
from core.variables.service import VariablesService

__all__ = [
    "VariableResolver",
    "UnmatchedBracesError",
    "VariableResolutionError",
    "VarResolver",
    "VariablesService",
    "get_state",
    "set_state_in_context",
]
