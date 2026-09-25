"""Автодискавери TaskIQ impl-модулей.

Импорт модуля с ``@platform_task`` регистрирует задачу на брокере очереди.
Здесь — только generic обход дерева модулей; apps-специфичная топология
(очередь → пакеты задач) живёт в ``apps/worker_manifest.py``.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from typing import Protocol, cast

from core.logging import get_logger

logger = get_logger(__name__)


class _PackageModule(Protocol):
    __name__: str
    __path__: list[str]


def import_task_modules(module_names: Iterable[str]) -> tuple[str, ...]:
    """Импортировать перечисленные модули/пакеты (рекурсивно для пакетов).

    Возвращает отсортированный кортеж импортированных имён — для CI/логов.
    """
    imported: set[str] = set()
    for root_name in module_names:
        root = importlib.import_module(root_name)
        imported.add(root_name)
        if not hasattr(root, "__path__"):
            continue
        package = cast(_PackageModule, cast(object, root))
        for info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
            _ = importlib.import_module(info.name)
            imported.add(info.name)
    return tuple(sorted(imported))


__all__ = ["import_task_modules"]
