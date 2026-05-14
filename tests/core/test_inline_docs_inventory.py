"""
Инварианты справочника inline Python: whitelist модулей и покрытие namespace.
"""

from __future__ import annotations

from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from apps.flows.src.services.runtime_namespace_doc import (
    build_runtime_namespace_global_variables,
)
from core.docs.data.python.globals import GLOBALS
from core.docs.data.python.modules import COMMON_MODULES, MODULE_METHODS


def test_common_modules_have_documentation_entries():
    missing = sorted(set(COMMON_MODULES) - set(MODULE_METHODS))
    assert not missing, (
        "Каждый модуль из whitelist импортов должен иметь карточку в MODULE_METHODS: "
        + ", ".join(missing)
    )


def test_namespace_keys_are_static_or_runtime_documented():
    documented = {entry["name"] for entry in GLOBALS}
    ns = PythonNamespaceBuilder().build()
    ns_keys = {k for k in ns if not k.startswith("__")}
    extras = {g.name for g in build_runtime_namespace_global_variables()}
    uncovered = sorted(ns_keys - documented - extras)
    assert not uncovered, (
        "Каждый символ sandbox-namespace должен быть в GLOBALS или в runtime_namespace_extras: "
        + ", ".join(uncovered)
    )
