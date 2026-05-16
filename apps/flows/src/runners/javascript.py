"""
JavaScriptCodeRunner - выполнение JavaScript кода.
Заготовка для будущей реализации.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.flows.src.runners.base import BaseCodeRunner

if TYPE_CHECKING:
    from core.state import ExecutionState


class JavaScriptCodeRunner(BaseCodeRunner):
    """
    Выполнение JavaScript кода.
    Заготовка - будет реализована позже.
    """

    language = "javascript"

    async def execute(
        self,
        code: str,
        state: ExecutionState,
        func_name: str = "run"
    ) -> Any:
        """
        Выполняет JavaScript код.

        Raises:
            NotImplementedError: JavaScript runner пока не реализован
        """
        raise NotImplementedError("JavaScript runner not implemented yet")

    async def execute_tool(
        self,
        code: str,
        args: dict[str, Any],
        state: ExecutionState | None = None,
    ) -> Any:
        """
        Выполняет JavaScript tool.

        Raises:
            NotImplementedError: JavaScript runner пока не реализован
        """
        raise NotImplementedError("JavaScript runner not implemented yet")

    def validate(self, code: str) -> tuple[bool, str | None]:
        """
        Валидирует JavaScript код.

        Raises:
            NotImplementedError: JavaScript validation пока не реализована
        """
        raise NotImplementedError("JavaScript validation not implemented yet")
