"""
Safe eval module for executing inline code.
"""

from core.errors import SafeEvalError

from apps.flows.src.eval.constants import BLOCKED_BUILTINS, BLOCKED_MODULES
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
    read_path_bytes,
    read_path_base64,
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
    # Ошибки
    "SafeEvalError",
    
    # Константы
    "BLOCKED_BUILTINS",
    "BLOCKED_MODULES",
    
    # State utils
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
    "read_path_bytes",
    "read_path_base64",
    
    # Wrappers
    "SafeLLMClient",
    "SafeContext",
    "SafeChannel",
    "HttpxModule",
    
    # Namespace & Compiler
    "PythonNamespaceBuilder",
    "PythonCompiler",
    
    # Legacy API
    "SafeEval",
    "compile_function",
    "safe_eval",
]
