"""
Safe eval module for executing inline code.
"""

from .safe_eval import (
    SafeContext,
    SafeEvalError,
    SafeLLMClient,
    compile_function,
    deep_copy_state,
    get_nested,
    merge_state,
    safe_eval,
    set_nested,
)

__all__ = [
    "compile_function",
    "safe_eval",
    "SafeEvalError",
    "SafeLLMClient",
    "SafeContext",
    "deep_copy_state",
    "merge_state",
    "get_nested",
    "set_nested",
]
