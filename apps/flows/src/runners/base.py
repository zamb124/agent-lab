"""
BaseCodeRunner - абстрактный базовый класс для выполнения кода.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import ExecutionState

from core.types import JsonObject, JsonValue


class BaseCodeRunner(ABC):
    """
    Базовый класс для выполнения кода.
    Единый интерфейс для Python, JavaScript и других языков.
    """

    language: str = "unknown"

    @abstractmethod
    async def execute(
        self,
        code: str,
        state: ExecutionState,
        func_name: str | None = None
    ) -> JsonValue:
        """
        Выполняет код.

        Аргументы:
            code: Исходный код
            state: ExecutionState
            func_name: Имя функции для вызова; None = первая функция в source

        Возвращает:
            JSON-совместимый результат выполнения
        """
        pass

    @abstractmethod
    async def execute_tool(
        self,
        code: str,
        args: JsonObject,
        state: ExecutionState | None = None,
        entrypoint: str | None = None,
    ) -> JsonValue:
        """
        Выполняет код tool.

        Аргументы:
            code: Исходный код tool
            args: Аргументы вызова
            state: ExecutionState (опционально)
            entrypoint: Имя функции-точки входа; None = первая функция в source

        Возвращает:
            JSON-совместимый результат выполнения
        """
        pass

    @abstractmethod
    def validate(self, code: str) -> tuple[bool, str | None]:
        """
        Валидирует код.

        Аргументы:
            code: Исходный код

        Возвращает:
            Tuple[bool, Optional[str]] — (valid, error_message)
        """
        pass
