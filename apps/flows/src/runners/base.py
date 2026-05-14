"""
BaseCodeRunner - абстрактный базовый класс для выполнения кода.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional, Tuple

if TYPE_CHECKING:
    from core.state import ExecutionState


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
        state: 'ExecutionState',
        func_name: str = "run"
    ) -> Any:
        """
        Выполняет код.

        Args:
            code: Исходный код
            state: ExecutionState
            func_name: Имя функции для вызова

        Returns:
            Результат выполнения (Any)
        """
        pass

    @abstractmethod
    async def execute_tool(
        self,
        code: str,
        args: dict,
        state: Optional['ExecutionState'] = None,
    ) -> Any:
        """
        Выполняет код tool.

        Args:
            code: Исходный код tool
            args: Аргументы вызова
            state: ExecutionState (опционально)

        Returns:
            Результат выполнения (Any)
        """
        pass

    @abstractmethod
    def validate(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        Валидирует код.

        Args:
            code: Исходный код

        Returns:
            Tuple[bool, Optional[str]] - (valid, error_message)
        """
        pass
