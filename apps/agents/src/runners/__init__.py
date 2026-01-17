"""
CodeRunner - унифицированное выполнение кода.
"""

from apps.agents.src.runners.base import BaseCodeRunner
from apps.agents.src.runners.python import PythonCodeRunner
from apps.agents.src.runners.javascript import JavaScriptCodeRunner

__all__ = [
    "BaseCodeRunner",
    "PythonCodeRunner",
    "JavaScriptCodeRunner",
]
