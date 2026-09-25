"""Ошибка сборки DI: все проблемы графа одним исключением."""

from __future__ import annotations

from collections.abc import Sequence
from typing import final


@final
class DiError(Exception):
    """Граф DI нельзя собрать; ``problems`` — каждая причина отдельной строкой."""

    def __init__(self, problems: Sequence[str]) -> None:
        if not problems:
            raise ValueError("DiError requires at least one problem")
        self.problems: tuple[str, ...] = tuple(problems)
        super().__init__("Service Kit DI cannot be built:\n  " + "\n  ".join(self.problems))
