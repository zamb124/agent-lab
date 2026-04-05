"""
Safe eval module for executing inline code.
"""

from core.errors import SafeEvalError

from apps.flows.src.eval.constants import (
    ALLOWED_BUILTINS,
    ALLOWED_IMPORT_ROOTS,
    FORBIDDEN_IMPORT_ROOTS,
    FUTURE_IMPORT_NAMES,
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
    set_nested,
)
from apps.flows.src.eval.wrappers import (
    HttpxModule,
    SafeChannel,
    SafeContext,
    SafeLLMClient,
)
from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from apps.flows.src.eval.compiler import PythonCompiler
from apps.flows.src.eval.safe_eval import (
    SafeEval,
    compile_function,
    safe_eval,
)

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
    "ask_user",
    "extract_json",
    "SafeLLMClient",
    "SafeContext",
    "SafeChannel",
    "HttpxModule",
    "PythonNamespaceBuilder",
    "PythonCompiler",
    "SafeEval",
    "compile_function",
    "safe_eval",
]
