"""
Имена классов исключений для whitelist `NodeConfig.exception_allow_types`.

Единый источник для UI (metadata API) и валидации конфига.
Соответствуют `type(exc).__name__` в Python.
"""

from enum import Enum


class ExceptionAbsorbAllowName(str, Enum):
    VALUE_ERROR = "ValueError"
    TYPE_ERROR = "TypeError"
    RUNTIME_ERROR = "RuntimeError"
    KEY_ERROR = "KeyError"
    ATTRIBUTE_ERROR = "AttributeError"
    ASSERTION_ERROR = "AssertionError"
    LOOKUP_ERROR = "LookupError"
    INDEX_ERROR = "IndexError"
    ZERO_DIVISION_ERROR = "ZeroDivisionError"
    IMPORT_ERROR = "ImportError"
    MODULE_NOT_FOUND_ERROR = "ModuleNotFoundError"
    NOT_IMPLEMENTED_ERROR = "NotImplementedError"
    OS_ERROR = "OSError"
    FILE_NOT_FOUND_ERROR = "FileNotFoundError"
    PERMISSION_ERROR = "PermissionError"
    CONNECTION_ERROR = "ConnectionError"
    TIMEOUT_ERROR = "TimeoutError"
    JSON_DECODE_ERROR = "JSONDecodeError"
    TOOL_EXECUTION_ERROR = "ToolExecutionError"
    SAFE_EVAL_ERROR = "SafeEvalError"
    NODE_EXECUTION_ERROR = "NodeExecutionError"
    EXTERNAL_API_ERROR = "ExternalAPIError"
    MAX_RETRIES_EXCEEDED_ERROR = "MaxRetriesExceededError"


def list_exception_absorb_allow_values() -> list[str]:
    return [m.value for m in ExceptionAbsorbAllowName]
