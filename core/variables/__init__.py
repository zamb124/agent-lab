"""
Система работы с переменными для промптов и агентов.
"""

from core.variables.engine import ResolutionEngine
from core.variables.models import (
    PlatformVariable,
    ResolutionContext,
    ResolvedVariable,
    ScopeCondition,
    ScopeField,
    ScopeOp,
    VariableEntry,
    VariableMap,
    VariableScopeOverride,
    VariableValueKind,
    VariableValuePayload,
    VariableValueSpec,
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

__all__ = [
    "PlatformVariable",
    "ResolutionContext",
    "ResolutionEngine",
    "ResolvedVariable",
    "ScopeCondition",
    "ScopeField",
    "ScopeOp",
    "VariableEntry",
    "VariableMap",
    "VariableResolver",
    "VariableScopeOverride",
    "VariableValueKind",
    "VariableValuePayload",
    "VariableValueSpec",
    "UnmatchedBracesError",
    "VariableResolutionError",
    "VarResolver",
    "get_state",
    "normalize_variables_map",
    "set_state_in_context",
    "variable_map_to_prompt_values",
]
