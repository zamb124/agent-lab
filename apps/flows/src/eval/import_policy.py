"""Проверка импортов для inline-кода (whitelist)."""

from __future__ import annotations

import ast
import builtins as b
from collections.abc import Mapping
from typing import Any

from apps.flows.src.eval.shim_registry import strict_shim_import_roots
from core.errors import SafeEvalError
from core.inline_python_eval_policy import (
    ALLOWED_IMPORT_ROOTS,
    FORBIDDEN_IMPORT_ROOTS,
    FUTURE_IMPORT_NAMES,
    import_module_top_level,
)

_MSG_IMPORT_PLATFORM_FORBIDDEN = (
    "В коде ноды нельзя подключать внутренние модули платформы через import. "
    "Нужные возможности уже в окружении: например reader, writer для файлов, llm для модели, "
    "channel и context — см. справку «Глобалы Python» в редакторе."
)

_BRIDGE_DENYLIST: frozenset[str] = frozenset({"datetime", "__builtins__", "__name__", "__doc__"})

def _bridge_denied(root: str) -> bool:
    if root in _BRIDGE_DENYLIST:
        return True
    if root.startswith("_"):
        return True
    return False


def filtered_namespace_import_roots(namespace: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(
        k
        for k in namespace
        if isinstance(k, str) and k.isidentifier() and not _bridge_denied(k)
    )


def get_default_namespace_import_roots() -> frozenset[str]:
    return frozenset()


def assert_module_import_allowed(
    module_name: str, *, namespace_keys: frozenset[str]
) -> None:
    if not module_name:
        raise SafeEvalError("Пустое имя модуля в import")
    root = import_module_top_level(module_name)
    if root in FORBIDDEN_IMPORT_ROOTS:
        raise SafeEvalError(_MSG_IMPORT_PLATFORM_FORBIDDEN)

    if root in strict_shim_import_roots() and module_name != root:
        raise SafeEvalError(
            f"Импорт '{module_name}' недоступен: `{root}` — платформенная подмена (inline shim), "
            f"только `import {root}` без подмодулей.",
        )

    if root in namespace_keys and module_name == root:
        return

    if root in namespace_keys and module_name != root:
        if root not in ALLOWED_IMPORT_ROOTS:
            raise SafeEvalError(
                f"Импорт '{module_name}' недоступен в sandbox; используйте `import {root}` "
                f"(без подмодулей) — это тот же объект, что в окружении ноды.",
            )

    if root not in ALLOWED_IMPORT_ROOTS:
        raise SafeEvalError(f"Import of '{module_name}' is not allowed")


def validate_import_nodes(tree: ast.AST, namespace_keys: frozenset[str]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert_module_import_allowed(alias.name, namespace_keys=namespace_keys)
            continue
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                raise SafeEvalError("Relative imports are not allowed in inline code")
            if not node.module:
                raise SafeEvalError("Invalid import: missing module")
            if node.module == "__future__":
                for alias in node.names:
                    if alias.name not in FUTURE_IMPORT_NAMES:
                        raise SafeEvalError(
                            f"from __future__ import {alias.name} is not allowed in inline code"
                        )
            assert_module_import_allowed(node.module, namespace_keys=namespace_keys)


def safe_inline_import(
    name: str,
    globals: object = None,
    locals: object = None,
    fromlist: tuple[Any, ...] = (),
    level: int = 0,
):
    if level != 0:
        raise SafeEvalError("Relative imports are not allowed in inline code")
    g: Mapping[str, object] | None = globals if isinstance(globals, dict) else None
    local_mapping: Mapping[str, object] | None = locals if isinstance(locals, dict) else None
    ns_keys = (
        filtered_namespace_import_roots(g)
        if g is not None
        else get_default_namespace_import_roots()
    )

    root = import_module_top_level(name)
    if (
        name == root
        and g is not None
        and root in g
        and not _bridge_denied(root)
        and not fromlist
    ):
        return g[root]

    assert_module_import_allowed(name, namespace_keys=ns_keys)

    return b.__import__(name, g, local_mapping, fromlist, level)
