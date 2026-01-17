"""
PythonCodeRunner - выполнение Python кода.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from apps.agents.src.eval.compiler import PythonCompiler
from apps.agents.src.eval.namespace import PythonNamespaceBuilder
from apps.agents.src.runners.base import BaseCodeRunner
from core.errors import SafeEvalError

if TYPE_CHECKING:
    from core.state import ExecutionState


class PythonCodeRunner(BaseCodeRunner):
    """
    Выполнение Python кода.
    """
    
    language = "python"
    
    def __init__(
        self,
        context: Optional[Any] = None,
        variables: Optional[Dict[str, Any]] = None,
        resources: Optional[Dict[str, Any]] = None,
    ):
        self.context = context
        self.variables = variables or {}
        self.resources = resources or {}
        self.namespace_builder = PythonNamespaceBuilder(
            context=context,
            variables=self.variables,
            resources=self.resources,
        )
        self.compiler = PythonCompiler(namespace_builder=self.namespace_builder)
    
    async def execute(
        self, 
        code: str, 
        state: 'ExecutionState', 
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
        
        if inspect.iscoroutinefunction(func):
            return await func(state)
        return func(state)
    
    async def execute_tool(
        self,
        code: str,
        args: dict,
        state: Optional['ExecutionState'] = None,
    ) -> Any:
        """
        Выполняет код tool.
        
        Поддерживает два формата:
        1. Функция: def execute(args, state) или async def execute(args, state)
        2. Класс: class MyTool(BaseTool) с методом execute
        
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
        
        if is_class:
            # Класс BaseTool
            tool_instance = target()
            return await tool_instance.run(args, state)
        
        # Функция
        func = target
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        
        # Если первый параметр - "args", передаём dict целиком
        if params and params[0] == "args":
            call_kwargs = {"args": args}
            if "state" in params:
                call_kwargs["state"] = state
            if inspect.iscoroutinefunction(func):
                return await func(**call_kwargs)
            return func(**call_kwargs)
        
        # Иначе распаковываем args в именованные параметры
        kwargs = dict(args)
        if "state" in params:
            kwargs["state"] = state
        
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)
    
    def validate(self, code: str) -> Tuple[bool, Optional[str]]:
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
