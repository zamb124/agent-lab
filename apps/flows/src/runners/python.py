"""
PythonCodeRunner - выполнение Python кода.
"""

from __future__ import annotations

import inspect
from typing import Any

from apps.flows.src.eval.compiler import PythonCompiler
from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from apps.flows.src.runners.base import BaseCodeRunner
from core.errors import SafeEvalError
from core.state import ExecutionState
from core.state.mutation_policy import (
    assert_frozen_fields_unchanged,
    snapshot_frozen_fields,
    user_code_state_mutation_guard,
)


class PythonCodeRunner(BaseCodeRunner):
    """
    Выполнение Python кода.
    """

    language = "python"

    def __init__(
        self,
        context: Any | None = None,
        variables: dict[str, Any] | None = None,
        resources: dict[str, Any] | None = None,
        base_tool_class: type | None = None,
    ):
        self.context = context
        self.variables = variables or {}
        self.resources = resources or {}
        self.namespace_builder = PythonNamespaceBuilder(
            context=context,
            variables=self.variables,
            resources=self.resources,
            base_tool_class=base_tool_class,
        )
        self.compiler = PythonCompiler(namespace_builder=self.namespace_builder)

    def _snapshot_frozen_if_state(self, state: ExecutionState | None) -> dict[str, Any] | None:
        if state is None or not isinstance(state, ExecutionState):
            return None
        return snapshot_frozen_fields(state)

    def _assert_frozen_if_needed(
        self, state: ExecutionState | None, snap: dict[str, Any] | None
    ) -> None:
        if snap is None or state is None or not isinstance(state, ExecutionState):
            return
        assert_frozen_fields_unchanged(state, snap)

    async def execute(
        self,
        code: str,
        state: ExecutionState,
        func_name: str = "run"
    ) -> Any:
        """
        Выполняет код ноды.

        Args:
            code: Python код с определением функции
            state: ExecutionState для передачи
            func_name: Имя функции для вызова

        Returns:
            Результат выполнения
        """
        func = self.compiler.compile(code, func_name, auto_find=True)
        snap = self._snapshot_frozen_if_state(state)
        with user_code_state_mutation_guard():
            if inspect.iscoroutinefunction(func):
                result = await func(state)
            else:
                result = func(state)
        self._assert_frozen_if_needed(state, snap)
        return result

    async def execute_tool(
        self,
        code: str,
        args: dict[str, Any],
        state: ExecutionState | None = None,
    ) -> Any:
        """
        Выполняет код tool.

        Поддерживает два формата:
        1. Функция: def execute(args, state) или async def execute(args, state) (или последняя top-level функция)
        2. Класс: class MyTool(BaseTool) с async run

        Args:
            code: Python код
            args: Аргументы вызова tool
            state: State (опционально)

        Returns:
            Результат выполнения
        """
        # Обновляем variables из state для доступа в коде
        if state is not None:
            self.namespace_builder.variables = dict(state.variables)

        target, is_class = self.compiler.compile_tool(code)

        snap = self._snapshot_frozen_if_state(state)
        with user_code_state_mutation_guard():
            if is_class:
                tool_instance = target()
                result = await tool_instance.run(args, state)
            else:
                func = target
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())

                if params and params[0] == "args":
                    call_kwargs: dict[str, Any] = {"args": args}
                    if "state" in params:
                        call_kwargs["state"] = state
                    if inspect.iscoroutinefunction(func):
                        result = await func(**call_kwargs)
                    else:
                        result = func(**call_kwargs)
                else:
                    kwargs = dict(args)
                    if "state" in params:
                        kwargs["state"] = state

                    if inspect.iscoroutinefunction(func):
                        result = await func(**kwargs)
                    else:
                        result = func(**kwargs)
        self._assert_frozen_if_needed(state, snap)
        return result

    def validate(self, code: str) -> tuple[bool, str | None]:
        """
        Валидирует Python код.

        Args:
            code: Python код

        Returns:
            Tuple[bool, Optional[str]] - (valid, error_message)
        """
        try:
            self.compiler.validate(code)
            return (True, None)
        except SafeEvalError as e:
            return (False, str(e))
