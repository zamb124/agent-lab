"""
Декоратор @tool для создания tools из функций.

Zero-Guess: все tools принимают ExecutionState.
"""

from __future__ import annotations

import inspect
import os
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, get_type_hints

from apps.agents.src.tools.base import BaseTool, ToolType
from apps.agents.src.mock import get_mock_for_tool
from apps.agents.src.models.tool_reference import CallParameter
from core.logging import get_logger

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)


def is_test_mode() -> bool:
    """Проверяет запущены ли тесты."""
    return os.environ.get("TESTING", "").lower() in ("true", "1", "yes")


class FunctionTool(BaseTool):
    """
    Tool созданный из функции через декоратор @tool.
    
    Хранит ссылку на оригинальную функцию для извлечения кода.
    """
    
    def __init__(
        self,
        func: Callable,
        name: str,
        description: str,
        tags: List[str],
        mock_response: Any = None,
        permission: Optional[str] = None,
        tool_type: ToolType = ToolType.TOOL,
        cost: float = 0.0,
        billing_name: Optional[str] = None,
        free_for_plans: Optional[List[str]] = None,
        tariff_limits: Optional[Dict[str, int]] = None,
    ):
        self._func = func
        self.name = name
        self.description = description
        self.tags = tags
        self._mock_response = mock_response
        self.permission = permission
        self.tool_type = tool_type
        self.args_schema = None
        self._parameters = self._extract_parameters(func)
        
        self.cost = cost
        self.billing_name = billing_name or name
        self.free_for_plans = free_for_plans or []
        self.tariff_limits = tariff_limits or {}
    
    def _extract_parameters(self, func: Callable) -> Dict[str, CallParameter]:
        """Извлекает параметры из type hints функции."""
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}
        
        sig = inspect.signature(func)
        params = {}
        
        for param_name, param in sig.parameters.items():
            # Пропускаем state - это служебный параметр
            if param_name == "state":
                continue
            
            param_type = hints.get(param_name, str)
            
            # Определяем тип для JSON schema
            type_mapping = {
                str: "string",
                int: "integer",
                float: "number",
                bool: "boolean",
                dict: "object",
                list: "array",
            }
            type_name = type_mapping.get(param_type, "string")
            
            # Описание из docstring если есть
            doc = func.__doc__ or ""
            description = f"Параметр {param_name}"
            
            # Проверяем обязательность параметра
            required = param.default is inspect.Parameter.empty
            
            params[param_name] = CallParameter(
                type=type_name,
                description=description,
                required=required,
            )
        
        return params
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """JSON схема параметров для LLM."""
        properties = {}
        required = []
        
        for name, param in self._parameters.items():
            properties[name] = {
                "type": param.type,
                "description": param.description,
            }
            if param.required:
                required.append(name)
        
        return {"type": "object", "properties": properties, "required": required}
    
    async def run(self, args: Dict[str, Any], state: "ExecutionState") -> Any:
        """
        Единственная точка входа для выполнения tool.
        
        Проверяет mock в порядке:
        1. state mock - из metadata агента
        2. mock_response из декоратора + TESTING=true
        """
        mock_result = get_mock_for_tool(state, self.name)
        if mock_result is not None:
            logger.debug(f"Tool {self.name}: using mock from state")
            return mock_result
        
        if is_test_mode() and self._mock_response is not None:
            logger.debug(f"Tool {self.name}: using mock from decorator")
            if callable(self._mock_response):
                result = self._mock_response(args)
                if inspect.iscoroutine(result):
                    return await result
                return result
            return self._mock_response
        
        logger.debug(f"Tool {self.name}: real mode")
        return await self._run_impl(args, state)
    
    async def _run_impl(self, args: Dict[str, Any], state: "ExecutionState") -> Any:
        """Выполняет функцию. State передается как ExecutionState."""
        sig = inspect.signature(self._func)
        
        if "state" in sig.parameters:
            if inspect.iscoroutinefunction(self._func):
                result = await self._func(**args, state=state)
            else:
                result = self._func(**args, state=state)
            return result
        
        if inspect.iscoroutinefunction(self._func):
            return await self._func(**args)
        return self._func(**args)
    
    def get_source_code(self) -> str:
        """Возвращает исходный код функции."""
        return inspect.getsource(self._func)


def tool(
    name: str,
    description: str,
    tags: List[str],
    mock_response: Any = None,
    permission: Optional[str] = None,
    tool_type: ToolType = ToolType.TOOL,
    cost: float = 0.0,
    billing_name: Optional[str] = None,
    free_for_plans: Optional[List[str]] = None,
    tariff_limits: Optional[Dict[str, int]] = None,
) -> Callable[[Callable], FunctionTool]:
    """
    Декоратор для создания tool из функции.
    
    Args:
        name: Имя tool (обязательный)
        description: Описание для LLM (обязательный)
        tags: Теги/категории (обязательный)
        mock_response: Mock ответ - строка, dict или callable
        permission: Группа с доступом к tool
        tool_type: Тип tool (TOOL, REASON, EXIT)
        cost: Стоимость использования tool (для биллинга)
        billing_name: Имя для биллинга (по умолчанию = name)
        free_for_plans: Список тарифов с бесплатным доступом
        tariff_limits: Лимиты использования по тарифам
    
    Использование:
        @tool(
            name="calculator",
            description="Вычисляет математические выражения",
            tags=["math"],
            mock_response="Результат: 42",
            cost=0.1,
            billing_name="math_calculator"
        )
        async def calculator(expression: str, state: dict = None) -> str:
            import math
            result = eval(expression, {'__builtins__': {}}, {'sin': math.sin})
            return f"Результат: {result}"
    """
    def decorator(func: Callable) -> FunctionTool:
        return FunctionTool(
            func=func,
            name=name,
            description=description,
            tags=tags,
            mock_response=mock_response,
            permission=permission,
            tool_type=tool_type,
            cost=cost,
            billing_name=billing_name,
            free_for_plans=free_for_plans,
            tariff_limits=tariff_limits,
        )
    return decorator

