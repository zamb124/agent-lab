"""
SafeEval - безопасное выполнение inline кода.

Legacy wrapper для обратной совместимости.
Новый код должен использовать PythonCodeRunner из apps.agents.src.runners.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from apps.agents.src.eval.compiler import PythonCompiler
from apps.agents.src.eval.namespace import PythonNamespaceBuilder
from apps.agents.src.runners.python import PythonCodeRunner

if TYPE_CHECKING:
    from core.state import ExecutionState

# Re-export для обратной совместимости
from apps.agents.src.eval.constants import BLOCKED_BUILTINS, BLOCKED_MODULES
from apps.agents.src.eval.state_utils import (
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
    read_file,
    read_file_base64,
    set_nested,
)
from apps.agents.src.eval.wrappers import (
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
    ):
        self.context = context
        self.variables = variables or {}
        self.resources = resources or {}
        self._runner = PythonCodeRunner(
            context=context,
            variables=self.variables,
            resources=self.resources,
        )
    
    def _build_namespace(self) -> Dict[str, Any]:
        """Создаёт namespace для выполнения кода."""
        return self._runner.namespace_builder.build()
    
    def _compile(self, code: str, func_name: str, auto_find: bool = True) -> Callable:
        """Компилирует код и возвращает функцию."""
        return self._runner.compiler.compile(code, func_name, auto_find=auto_find)
    
    async def execute_node(self, code: str, state: 'ExecutionState') -> Any:
        """
        Выполняет код ноды (ищет функцию run).
        
        Args:
            code: Код функции
            state: ExecutionState для передачи
            
        Returns:
            Результат выполнения
        """
        return await self._runner.execute(code, state, func_name="run")
    
    async def execute_tool(self, code: str, args: Dict[str, Any], state: Optional['ExecutionState'] = None) -> Any:
        """
        Выполняет код tool.
        
        Args:
            code: Код функции или класса
            args: Аргументы вызова tool
            state: State (опционально)
            
        Returns:
            Результат выполнения
        """
        return await self._runner.execute_tool(code, args, state)


def compile_function(
    code: str,
    func_name: str = "run",
    context: Optional[Any] = None,
    variables: Optional[Dict[str, Any]] = None,
    auto_find: bool = False,
) -> Callable:
    """Компилирует код и возвращает функцию."""
    namespace_builder = PythonNamespaceBuilder(context=context, variables=variables or {})
    compiler = PythonCompiler(namespace_builder=namespace_builder)
    return compiler.compile(code, func_name, auto_find=auto_find)


async def safe_eval(
    code: str,
    state: 'ExecutionState',
    context: Optional[Any] = None,
    func_name: str = "run",
) -> Any:
    """Безопасно выполняет inline код ноды."""
    variables = state.variables if hasattr(state, 'variables') else {}
    runner = PythonCodeRunner(context=context, variables=variables)
    return await runner.execute(code, state, func_name=func_name)
