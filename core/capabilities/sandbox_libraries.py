"""Единый канон библиотек и builtins isolated code runners.

Runners и language-native LSP workspace читают эти списки.
Не дублировать allowlist в UI или в worker вручную — меняй здесь.
"""

from __future__ import annotations

from core.capabilities.models import CapabilityLanguage

PYTHON_ALLOWED_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "__future__",
        "asyncio",
        "array",
        "ast",
        "base64",
        "bisect",
        "calendar",
        "collections",
        "contextlib",
        "copy",
        "csv",
        "dataclasses",
        "datetime",
        "dateutil",
        "decimal",
        "defusedxml",
        "difflib",
        "email.message",
        "email.parser",
        "enum",
        "fnmatch",
        "fractions",
        "functools",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "math",
        "numbers",
        "numpy",
        "openpyxl",
        "operator",
        "pandas",
        "pathlib",
        "pprint",
        "random",
        "re",
        "secrets",
        "statistics",
        "string",
        "struct",
        "textwrap",
        "time",
        "tomllib",
        "traceback",
        "typing",
        "unicodedata",
        "urllib.parse",
        "uuid",
        "xml.etree",
        "xml.etree.ElementTree",
        "yaml",
        "zipfile",
        "zlib",
        "zoneinfo",
        "bs4",
    }
)

PYTHON_FORBIDDEN_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "apps",
        "core",
        "ctypes",
        "httpx",
        "importlib",
        "multiprocessing",
        "os",
        "pickle",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "urllib.request",
        "urllib.error",
    }
)

PYTHON_SANDBOX_BUILTINS: tuple[str, ...] = (
    "BaseException",
    "Exception",
    "AssertionError",
    "AttributeError",
    "ImportError",
    "IndexError",
    "KeyError",
    "NameError",
    "NotImplementedError",
    "PermissionError",
    "RuntimeError",
    "TypeError",
    "ValueError",
    "ZeroDivisionError",
    "abs",
    "all",
    "any",
    "bin",
    "bool",
    "bytearray",
    "bytes",
    "callable",
    "chr",
    "classmethod",
    "dict",
    "divmod",
    "enumerate",
    "filter",
    "float",
    "format",
    "frozenset",
    "hash",
    "hex",
    "int",
    "iter",
    "isinstance",
    "len",
    "list",
    "map",
    "max",
    "min",
    "next",
    "object",
    "oct",
    "ord",
    "pow",
    "print",
    "property",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "staticmethod",
    "str",
    "sum",
    "tuple",
    "type",
    "zip",
    "FlowInterrupt",
)

PYTHON_FORBIDDEN_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "hasattr",
        "input",
        "locals",
        "memoryview",
        "open",
        "setattr",
        "vars",
    }
)

NODE_SAFE_GLOBALS: tuple[str, ...] = (
    "JSON",
    "Math",
    "Date",
    "Map",
    "Set",
    "WeakMap",
    "WeakSet",
    "Object",
    "Array",
    "Number",
    "String",
    "Boolean",
    "Error",
    "TypeError",
    "RangeError",
    "URIError",
    "URL",
    "URLSearchParams",
    "TextEncoder",
    "TextDecoder",
    "parseInt",
    "parseFloat",
    "isNaN",
    "isFinite",
    "encodeURI",
    "decodeURI",
    "encodeURIComponent",
    "decodeURIComponent",
    "undefined",
    "NaN",
    "Infinity",
    "console",
    "Promise",
    "setTimeout",
    "clearTimeout",
    "ArrayBuffer",
    "DataView",
    "BigInt",
    "crypto",
    "structuredClone",
    "Int8Array",
    "Uint8Array",
    "Uint8ClampedArray",
    "Int16Array",
    "Uint16Array",
    "Int32Array",
    "Uint32Array",
    "Float32Array",
    "Float64Array",
    "Intl",
)

NODE_ALLOWED_PACKAGES: frozenset[str] = frozenset(
    {
        "lodash",
        "csv-parse",
        "csv-parse/sync",
        "uuid",
        "date-fns",
    }
)

CSHARP_ALLOWED_USINGS: frozenset[str] = frozenset(
    {
        "System",
        "System.Collections.Generic",
        "System.Globalization",
        "System.Linq",
        "System.Text",
        "System.Text.Json",
        "System.Text.RegularExpressions",
        "System.Threading.Tasks",
        "System.Xml.Linq",
        "System.Buffers",
        "System.Collections.Immutable",
    }
)

GO_FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "C",
        "net",
        "net/http",
        "net/url",
        "os",
        "os/exec",
        "path/filepath",
        "plugin",
        "reflect",
        "runtime",
        "syscall",
        "unsafe",
    }
)

GO_ALLOWED_STDLIB_MODULES: tuple[str, ...] = (
    "bufio",
    "bytes",
    "cmp",
    "context",
    "encoding/base64",
    "encoding/csv",
    "encoding/hex",
    "encoding/json",
    "encoding/xml",
    "encoding/binary",
    "errors",
    "fmt",
    "html",
    "io",
    "log",
    "maps",
    "math",
    "math/big",
    "path",
    "regexp",
    "slices",
    "sort",
    "strconv",
    "strings",
    "sync",
    "time",
    "unicode",
    "unicode/utf8",
)


def is_allowed_go_import(package: str) -> bool:
    """Разрешён ли Go import: allowlist stdlib, плюс deny-list как второй замок."""
    if not package:
        return False
    if package in GO_FORBIDDEN_IMPORTS or package.split("/", 1)[0] in GO_FORBIDDEN_IMPORTS:
        return False
    return package in GO_ALLOWED_STDLIB_MODULES


def is_allowed_python_import(name: str, extra_roots: frozenset[str] | None = None) -> bool:
    """Разрешён ли import по префиксу (urllib.parse да, urllib.request нет)."""
    if not name:
        return False
    if name.split(".", 1)[0] in PYTHON_FORBIDDEN_IMPORT_ROOTS:
        return False
    if name in PYTHON_FORBIDDEN_IMPORT_ROOTS:
        return False
    allowed = PYTHON_ALLOWED_IMPORT_ROOTS if extra_roots is None else PYTHON_ALLOWED_IMPORT_ROOTS | extra_roots
    parts = name.split(".")
    for index in range(len(parts), 0, -1):
        prefix = ".".join(parts[:index])
        if prefix in allowed:
            return True
        if prefix in PYTHON_FORBIDDEN_IMPORT_ROOTS:
            return False
    return False


def sandbox_modules_for_language(language: CapabilityLanguage) -> list[str]:
    if language == "python":
        return sorted(PYTHON_ALLOWED_IMPORT_ROOTS)
    if language in {"javascript", "typescript"}:
        return sorted(NODE_ALLOWED_PACKAGES)
    if language == "go":
        return list(GO_ALLOWED_STDLIB_MODULES)
    if language == "csharp":
        return sorted(CSHARP_ALLOWED_USINGS)
    raise ValueError(f"Unsupported language: {language}")


def sandbox_builtins_for_language(language: CapabilityLanguage) -> list[str]:
    if language == "python":
        return list(PYTHON_SANDBOX_BUILTINS)
    if language in {"javascript", "typescript"}:
        return list(NODE_SAFE_GLOBALS)
    if language == "go":
        return []
    if language == "csharp":
        return sorted(CSHARP_ALLOWED_USINGS)
    raise ValueError(f"Unsupported language: {language}")
