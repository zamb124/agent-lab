"""
Реестр inline-подмен: объекты не из site-packages, а из платформенных обёрток.

Имена и фабрики — единственная точка для `import <name>` (мост в import_policy) и
заполнения namespace в PythonNamespaceBuilder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apps.flows.src.eval.wrappers import HttpxModule, SafeLLMClient


@dataclass(frozen=True, slots=True)
class InlineShimSpec:
    """
    `import <name>` в sandbox возвращает `factory(builder)`; не настоящий пакет CPython.
    `forbid_submodule_imports`: запретить `import name.sub` (объект цельный, без подмодулей).
    """

    name: str
    forbid_submodule_imports: bool
    factory: Callable[[Any], Any]


def _httpx_factory(_builder: Any) -> Any:
    return HttpxModule()


def _llm_factory(_builder: Any) -> Any:
    return SafeLLMClient()


INLINE_SHIMS: tuple[InlineShimSpec, ...] = (
    InlineShimSpec("httpx", True, _httpx_factory),
    InlineShimSpec("llm", True, _llm_factory),
)


def inline_shim_map() -> dict[str, InlineShimSpec]:
    return {s.name: s for s in INLINE_SHIMS}


def strict_shim_import_roots() -> frozenset[str]:
    return frozenset(s.name for s in INLINE_SHIMS if s.forbid_submodule_imports)


def get_inline_shim(name: str) -> InlineShimSpec | None:
    return inline_shim_map().get(name)


def apply_inline_shims(builder: Any, namespace: dict[str, Any]) -> None:
    for spec in INLINE_SHIMS:
        namespace[spec.name] = spec.factory(builder)
