"""
SafeEval - безопасное выполнение inline кода.

Legacy wrapper для обратной совместимости.
Новый код должен использовать PythonCodeRunner из apps.flows.src.runners.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from apps.flows.src.eval.compiler import PythonCompiler
from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from apps.flows.src.runners.python import PythonCodeRunner

if TYPE_CHECKING:
    from core.state import ExecutionState

from apps.flows.src.eval.constants import (
    ALLOWED_BUILTINS,
    ALLOWED_IMPORT_ROOTS,
    FORBIDDEN_IMPORT_ROOTS,
    FUTURE_IMPORT_NAMES,
)
from apps.flows.src.eval.state_utils import (
    add_agent_message,
    add_user_message,
    ask_user,
    deep_copy_state,
    extract_json,
    get_files,
    get_messages,
    get_nested,
    get_tool_result,
    get_user,
    merge_state,
    set_nested,
)
from apps.flows.src.eval.wrappers import (
    HttpxModule,
    SafeChannel,
    SafeContext,
    SafeLLMClient,
)


class SafeEval:
    """
    Legacy класс для безопасного выполнения inline кода.

    Используйте PythonCodeRunner для нового кода.
    """

    def __init__(
        self,
        context: Optional[Any] = None,
        variables: Optional[Dict[str, Any]] = None,
        resources: Optional[Dict[str, Any]] = None,
        base_tool_class: Optional[type] = None,
    ):
        self.context = context
        self.variables = variables or {}
        self.resources = resources or {}
        self._runner = PythonCodeRunner(
            context=context,
            variables=self.variables,
            resources=self.resources,
            base_tool_class=base_tool_class,
        )

    def _build_namespace(self) -> Dict[str, Any]:
        return self._runner.namespace_builder.build()

    def _compile(self, code: str, func_name: str, auto_find: bool = True) -> Callable:
        return self._runner.compiler.compile(code, func_name, auto_find=auto_find)

    async def execute_node(self, code: str, state: "ExecutionState") -> Any:
        return await self._runner.execute(code, state, func_name="run")

    async def execute_tool(
        self, code: str, args: Dict[str, Any], state: Optional["ExecutionState"] = None
    ) -> Any:
        return await self._runner.execute_tool(code, args, state)


def compile_function(
    code: str,
    func_name: str = "run",
    context: Optional[Any] = None,
    variables: Optional[Dict[str, Any]] = None,
    auto_find: bool = False,
    base_tool_class: Optional[type] = None,
    *,
    strip_platform_imports: bool = True,
) -> Callable:
    """Компилирует код и возвращает функцию."""
    namespace_builder = PythonNamespaceBuilder(
        context=context,
        variables=variables or {},
        base_tool_class=base_tool_class,
    )
    compiler = PythonCompiler(
        namespace_builder=namespace_builder,
        strip_platform_imports=strip_platform_imports,
    )
    return compiler.compile(code, func_name, auto_find=auto_find)


async def safe_eval(
    code: str,
    state: "ExecutionState",
    context: Optional[Any] = None,
    func_name: str = "run",
) -> Any:
    """Безопасно выполняет inline код ноды."""
    variables = state.variables if hasattr(state, "variables") else {}
    runner = PythonCodeRunner(context=context, variables=variables)
    return await runner.execute(code, state, func_name=func_name)
