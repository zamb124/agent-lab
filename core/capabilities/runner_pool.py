"""Размер пула code runner из Settings."""

from __future__ import annotations

import os
from typing import Literal

from core.config import get_settings

CodeRunnerKind = Literal["python", "node", "go", "csharp"]


def code_runner_pool_size(kind: CodeRunnerKind) -> int:
    """Число worker или слотов сборки. Незаданное поле — от 2 до 8 по CPU."""
    pool = get_settings().code_runner
    match kind:
        case "python":
            configured = pool.python_workers
            floor = 1
        case "node":
            configured = pool.node_workers
            floor = 1
        case "go":
            configured = pool.go_workers
            floor = 2
        case "csharp":
            configured = pool.csharp_workers
            floor = 2
    if configured is None:
        return _default_code_runner_pool_size()
    return max(floor, configured)


def _default_code_runner_pool_size() -> int:
    cpu = os.cpu_count()
    if cpu is None:
        cpu = 2
    return max(2, min(8, cpu))


__all__ = ["CodeRunnerKind", "code_runner_pool_size"]
