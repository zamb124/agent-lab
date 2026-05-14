"""
Variables - управление переменными агентов.
"""

from core.variables import (
    UnmatchedBracesError,
    VariableResolutionError,
    VariableResolver,
    VariablesService,
    VarResolver,
    get_state,
    set_state_in_context,
)

__all__ = [
    "VariableResolver",
    "VariableResolutionError",
    "VarResolver",
    "UnmatchedBracesError",
    "VariablesService",
    "get_state",
    "set_state_in_context",
]
