"""Статические сканеры контракта кода по языкам.

Python разбирается через `ast`. Языки C-семейства (JavaScript/TypeScript, Go,
C#) разбираются набором целевых регулярных выражений по идиомам доступа к
`state` (`state.field`, `state["field"]`) и возврату объектов/словарей.

Результат кэшируется по (language, sha256(code)): один и тот же код анализируется
один раз.
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Iterable
from typing import cast

from core.code_contract.models import CodeContract

_LANG_C_LIKE: frozenset[str] = frozenset(
    {"javascript", "typescript", "js", "ts", "go", "golang", "csharp", "cs", "c#"}
)

_STATE_ATTR_ASSIGN = re.compile(r"\bstate\.([A-Za-z_][A-Za-z0-9_]*)\s*(?:[-+*/|&^]?=|:=)(?!=)")
_STATE_ITEM_ASSIGN = re.compile(
    r"""\bstate\[\s*['"]([A-Za-z_][A-Za-z0-9_.\-]*)['"]\s*\]\s*(?:[-+*/|&^]?=|:=)(?!=)"""
)
_STATE_GET_READ = re.compile(
    r"""\bstate\.get\s*\(\s*['"]([A-Za-z_][A-Za-z0-9_.\-]*)['"]"""
)
_STATE_ATTR_READ = re.compile(
    r"\bstate\.([A-Za-z_][A-Za-z0-9_]*)(?!\s*\()",
)
_STATE_ITEM_READ = re.compile(r"""\bstate\[\s*['"]([A-Za-z_][A-Za-z0-9_.\-]*)['"]\s*\]""")
_VARIABLES_ITEM_ASSIGN = re.compile(
    r"""\bvariables\[\s*['"]([A-Za-z_][A-Za-z0-9_.\-]*)['"]\s*\]\s*(?:[-+*/|&^]?=|:=)(?!=)"""
)
_RETURN_OBJECT = re.compile(
    r"\breturn\s+(?:new\s+(?:[A-Za-z_][\w.]*\s*)?)?\{([^}]{0,4000})\}", re.DOTALL
)
_OBJECT_KEY = re.compile(r"""['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?\s*[:=]""")

_STATE_METHOD_NAMES: frozenset[str] = frozenset(
    {"get", "keys", "values", "items", "pop", "setdefault", "update", "clear"},
)
_CACHE: dict[tuple[str, str], CodeContract] = {}
_CACHE_MAX = 512


def scan_code_contract(language: str, code: str) -> CodeContract:
    """Возвращает статический контракт кода для языка.

    Пустой код даёт пустой контракт. Неизвестный язык обрабатывается как
    C-подобный (общие идиомы `state`).
    """

    normalized_language = (language or "").strip().lower()
    if not code or not code.strip():
        return CodeContract(
            reads=[],
            optional_reads=[],
            writes=[],
            variable_writes=[],
            return_keys=[],
        )
    digest = hashlib.sha256(f"{normalized_language}\x00{code}".encode()).hexdigest()
    cache_key = (normalized_language, digest)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached
    if normalized_language in {"python", "py"}:
        contract = _scan_python(code)
    else:
        contract = _scan_c_like(code)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[cache_key] = contract
    return contract


def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})


def _scan_python(code: str) -> CodeContract:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _scan_c_like(code)
    writes: set[str] = set()
    reads: set[str] = set()
    optional_reads: set[str] = set()
    variable_writes: set[str] = set()
    return_keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                path = _python_state_target_path(target)
                if path:
                    writes.add(path)
                var_key = _python_variables_subscript_key(target)
                if var_key:
                    variable_writes.add(var_key)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "update" and _python_is_state_expr(node.func.value):
                if node.args and isinstance(node.args[0], ast.Dict):
                    for key_node in node.args[0].keys:
                        key = _python_literal_string(key_node)
                        if key:
                            writes.add(key)
            elif (
                node.func.attr == "update"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "variables"
            ):
                if node.args and isinstance(node.args[0], ast.Dict):
                    for key_node in node.args[0].keys:
                        key = _python_literal_string(key_node)
                        if key:
                            variable_writes.add(key)
            elif node.func.attr == "get" and _python_is_state_expr(node.func.value):
                if node.args:
                    key = _python_literal_string(node.args[0])
                    if key:
                        optional_reads.add(key)
        if isinstance(node, ast.Call):
            if len(node.args) >= 2 and _python_is_state_expr(node.args[0]):
                key = _python_literal_string(node.args[1])
                if key:
                    reads.add(key)
        if isinstance(node, ast.Attribute) and _python_is_state_expr(node.value):
            if node.attr not in _STATE_METHOD_NAMES:
                reads.add(node.attr)
        if isinstance(node, ast.Subscript) and _python_is_state_expr(node.value):
            key = _python_literal_string(node.slice)
            if key:
                reads.add(key)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key_node in node.value.keys:
                key = _python_literal_string(key_node)
                if key:
                    return_keys.add(key)
    return CodeContract(
        reads=_sorted_unique(reads),
        optional_reads=_sorted_unique(optional_reads),
        writes=_sorted_unique(writes),
        variable_writes=_sorted_unique(variable_writes),
        return_keys=_sorted_unique(return_keys),
    )


def _python_variables_subscript_key(target: ast.AST) -> str | None:
    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
        if target.value.id == "variables":
            return _python_literal_string(target.slice)
    return None


def _python_state_target_path(target: ast.AST) -> str | None:
    if isinstance(target, ast.Attribute) and _python_is_state_expr(target.value):
        return target.attr
    if isinstance(target, ast.Subscript) and _python_is_state_expr(target.value):
        return _python_literal_string(target.slice)
    return None


def _python_is_state_expr(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "state"


def _python_literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
        return node.value
    return None


def _regex_capture_groups(pattern: re.Pattern[str], code: str) -> list[str]:
    return cast(list[str], pattern.findall(code))


def _scan_c_like(code: str) -> CodeContract:
    writes: set[str] = set()
    writes.update(_regex_capture_groups(_STATE_ATTR_ASSIGN, code))
    writes.update(_regex_capture_groups(_STATE_ITEM_ASSIGN, code))
    variable_writes: set[str] = set()
    variable_writes.update(_regex_capture_groups(_VARIABLES_ITEM_ASSIGN, code))
    reads: set[str] = set()
    optional_reads: set[str] = set()
    optional_reads.update(_regex_capture_groups(_STATE_GET_READ, code))
    for attr_key in _regex_capture_groups(_STATE_ATTR_READ, code):
        if attr_key not in _STATE_METHOD_NAMES:
            reads.add(attr_key)
    reads.update(_regex_capture_groups(_STATE_ITEM_READ, code))
    return_keys: set[str] = set()
    for match in _RETURN_OBJECT.finditer(code):
        body = match.group(1)
        return_keys.update(_OBJECT_KEY.findall(body))
    return CodeContract(
        reads=_sorted_unique(reads),
        optional_reads=_sorted_unique(optional_reads),
        writes=_sorted_unique(writes),
        variable_writes=_sorted_unique(variable_writes),
        return_keys=_sorted_unique(return_keys),
    )


__all__ = ["scan_code_contract"]
