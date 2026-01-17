"""
Константы безопасности для выполнения inline кода.
"""

from typing import FrozenSet

# Запрещённые модули - потенциально опасны для системы
BLOCKED_MODULES: FrozenSet[str] = frozenset({
    "os",
    "sys",
    "subprocess",
    "shutil",
    "socket",
    "pickle",
    "marshal",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
    "resource",
    "pty",
    "fcntl",
    "termios",
    "syslog",
    "posix",
    "nt",
    "_thread",
    "builtins",
    "__builtin__",
    "importlib",
    "code",
    "codeop",
    "compileall",
    "py_compile",
})

# Запрещённые builtins - позволяют обойти ограничения
BLOCKED_BUILTINS: FrozenSet[str] = frozenset({
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "classmethod",
    "staticmethod",
    "property",
    "super",
    "object",
    "memoryview",
    "bytearray",
    "breakpoint",
    "input",
    "help",
    "exit",
    "quit",
})
