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
    VariableResolutionError,
    VariableResolver,
    VarResolver,
    get_state,
    set_state_in_context,
)
from core.variables.template_scan import (
    TemplateScanResult,
    TemplateVariableRef,
    UnmatchedBracesError,
    scan_prompt_template,
    unmatched_brace_message,
)

__all__ = [
    "PlatformVariable",
    "ResolutionContext",
    "ResolutionEngine",
    "ResolvedVariable",
    "ScopeCondition",
    "ScopeField",
    "ScopeOp",
    "TemplateScanResult",
    "TemplateVariableRef",
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
    "scan_prompt_template",
    "set_state_in_context",
    "unmatched_brace_message",
    "variable_map_to_prompt_values",
]
