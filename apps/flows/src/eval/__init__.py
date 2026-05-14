"""
Safe eval module for executing inline code.
"""

from apps.flows.src.eval.compiler import PythonCompiler
from apps.flows.src.eval.constants import (
    ALLOWED_BUILTINS,
    ALLOWED_IMPORT_ROOTS,
    FORBIDDEN_IMPORT_ROOTS,
    FUTURE_IMPORT_NAMES,
)
from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from apps.flows.src.eval.safe_eval import (
    SafeEval,
    compile_function,
    safe_eval,
)
from apps.flows.src.eval.shim_registry import (
    INLINE_SHIMS,
    get_inline_shim,
    strict_shim_import_roots,
)
from apps.flows.src.eval.state_utils import (
    add_agent_message,
    add_user_message,
    ask_user,
    deep_copy_state,
    extract_json,
    get_files,
    get_messages,
    get_nested,
    get_tool_result,
    get_user,
    merge_state,
    pop_ui_events,
    push_ui_event,
    push_ui_events,
    set_nested,
)
from apps.flows.src.eval.wrappers import (
    HttpxModule,
    SafeChannel,
    SafeContext,
    SafeLLMClient,
)
from core.errors import SafeEvalError

__all__ = [
    "SafeEvalError",
    "ALLOWED_BUILTINS",
    "ALLOWED_IMPORT_ROOTS",
    "FORBIDDEN_IMPORT_ROOTS",
    "FUTURE_IMPORT_NAMES",
    "deep_copy_state",
    "merge_state",
    "get_nested",
    "set_nested",
    "get_files",
    "get_user",
    "get_tool_result",
    "get_messages",
    "add_user_message",
    "add_agent_message",
    "push_ui_event",
    "push_ui_events",
    "pop_ui_events",
    "ask_user",
    "extract_json",
    "SafeLLMClient",
    "SafeContext",
    "SafeChannel",
    "HttpxModule",
    "INLINE_SHIMS",
    "get_inline_shim",
    "strict_shim_import_roots",
    "PythonNamespaceBuilder",
    "PythonCompiler",
    "SafeEval",
    "compile_function",
    "safe_eval",
]
