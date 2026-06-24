"""
Система работы с переменными для промптов и агентов.
"""

from core.variables.models import (
    VariableEntry,
    VariableMap,
    normalize_variables_map,
    variable_map_to_prompt_values,
)
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
    "VariableEntry",
    "VariableMap",
    "VariableResolver",
    "UnmatchedBracesError",
    "VariableResolutionError",
    "VarResolver",
    "VariablesService",
    "get_state",
    "normalize_variables_map",
    "set_state_in_context",
    "variable_map_to_prompt_values",
]
