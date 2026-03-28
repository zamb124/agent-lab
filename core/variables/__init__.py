"""
Система работы с переменными для промптов и агентов.
"""

from core.variables.resolver import (
    VariableResolver,
    UnmatchedBracesError,
    VariableResolutionError,
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
