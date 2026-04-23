"""
Символы sandbox-namespace, не перечисленные в статическом core/docs/data/python/globals.py.
"""

from __future__ import annotations

import types
from typing import List

from core.docs.models import GlobalVariable


def _type_label(obj: object) -> str:
    if isinstance(obj, types.ModuleType):
        return f"module:{getattr(obj, '__name__', type(obj).__name__)}"
    if isinstance(obj, type):
        return f"class:{obj.__name__}"
    return type(obj).__name__


def build_runtime_namespace_global_variables() -> List[GlobalVariable]:
    from core.docs.data.python.globals import GLOBALS as STATIC_GLOBALS
    from apps.flows.src.eval.namespace import PythonNamespaceBuilder

    documented = {g["name"] for g in STATIC_GLOBALS}
    ns = PythonNamespaceBuilder().build()
    out: List[GlobalVariable] = []
    for name in sorted(ns.keys()):
        if name.startswith("__"):
            continue
        if name in documented:
            continue
        obj = ns[name]
        out.append(
            GlobalVariable(
                name=name,
                type=_type_label(obj),
                doc=(
                    "Доступно в sandbox inline-кода (`PythonNamespaceBuilder.build`). "
                    "Публичные символы описываются в `core/docs/data/python/globals.py`."
                ),
                perspective=["editor", "flow", "tool", "node"],
                tags=["runtime_namespace"],
            )
        )
    return out
