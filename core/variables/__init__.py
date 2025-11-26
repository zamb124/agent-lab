"""
Variables - управление переменными компаний.
"""

from core.variables.service import VariablesService
from core.variables.resolver import VariableResolver, get_state, set_state_in_context

__all__ = [
    "VariablesService",
    "VariableResolver",
    "get_state",
    "set_state_in_context",
]

