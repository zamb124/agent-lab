"""
Variables - управление переменными агентов.
"""

from core.variables import (
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
    "VariableResolutionError",
    "VarResolver",
    "UnmatchedBracesError",
    "VariablesService",
    "get_state",
    "set_state_in_context",
]
