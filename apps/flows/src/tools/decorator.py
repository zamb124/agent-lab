"""
Декоратор @tool для создания tools из функций.

Zero-Guess: все tools принимают ExecutionState.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from types import FunctionType
from typing import TYPE_CHECKING, TypeAlias, TypeVar, override

from pydantic import BaseModel

from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.tools.base import (
    BaseTool,
    ToolArguments,
    ToolFunctionResult,
    ToolParametersSchema,
    ToolResult,
)
from apps.flows.src.tools.json_schema_parameters import pydantic_model_to_parameters_schema
from core.logging import get_logger
from core.types import require_json_object, require_json_value

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)
Permission = str | list[str] | None

ToolFunction: TypeAlias = Callable[..., ToolFunctionResult]
F = TypeVar("F", bound=ToolFunction)


class FunctionTool(BaseTool):
    """
    Tool созданный из функции через декоратор @tool.

    Хранит ссылку на оригинальную функцию для извлечения кода.
    """

    def __init__(
        self,
        func: ToolFunction,
        name: str,
        description: str,
        tags: list[str],
        parameters_model: type[BaseModel],
        permission: Permission = None,
        react_role: ReactToolRole = ReactToolRole.STANDARD,
        cost: float = 0.0,
        billing_name: str | None = None,
        free_for_plans: list[str] | None = None,
        tariff_limits: dict[str, int] | None = None,
    ):
        self._func: ToolFunction = func
        self.name: str = name
        self.description: str = description
        self.tags: list[str] = tags
        self.permission: Permission = permission
        self.react_role: ReactToolRole = react_role
        self.parameters_model: type[BaseModel] | None = parameters_model

        self.cost: float = cost
        self.billing_name: str = billing_name or name
        self.free_for_plans: list[str] = free_for_plans or []
        self.tariff_limits: dict[str, int] = tariff_limits or {}

    @property
    @override
    def parameters(self) -> ToolParametersSchema:
        """JSON Schema параметров для LLM."""
        if self.parameters_model is None:
            raise RuntimeError(f"Tool '{self.name}' requires parameters_model")
        return pydantic_model_to_parameters_schema(self.parameters_model)

    @override
    async def run(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """
        Единственная точка входа для выполнения tool.
        """
        logger.debug(f"Tool {self.name}: run")
        return require_json_value(
            await self._run_impl(args, state),
            f"tool.{self.name}.result",
        )

    @override
    async def _run_impl(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """Выполняет функцию. State передается как ExecutionState."""
        sig = inspect.signature(self._func)
        if self.parameters_model is None:
            raise RuntimeError(f"Tool '{self.name}' requires parameters_model")
        validated = self.parameters_model.model_validate(args)
        call_kw = require_json_object(
            validated.model_dump(mode="json"),
            f"tool.{self.name}.validated_args",
        )

        if "state" in sig.parameters:
            result = self._func(**call_kw, state=state)
        else:
            result = self._func(**call_kw)
        if inspect.isawaitable(result):
            result = await result
        return require_json_value(result, f"tool.{self.name}.result")

    def get_source_code(self) -> str:
        """Возвращает исходный код функции."""
        return inspect.getsource(self._func)

    @property
    def source_function(self) -> FunctionType:
        """Оригинальная Python-функция для анализа исходного модуля."""
        if not isinstance(self._func, FunctionType):
            raise TypeError(f"Tool '{self.name}' source is not a Python function")
        return self._func


def tool(
    name: str,
    description: str,
    tags: list[str],
    parameters_model: type[BaseModel],
    permission: Permission = None,
    react_role: ReactToolRole = ReactToolRole.STANDARD,
    cost: float = 0.0,
    billing_name: str | None = None,
    free_for_plans: list[str] | None = None,
    tariff_limits: dict[str, int] | None = None,
    listed_in_platform_tool_docs: bool = True,
) -> Callable[[F], FunctionTool]:
    """
    Декоратор для создания tool из функции.

    Args:
        name: Имя tool (обязательный)
        description: Описание для LLM (обязательный)
        tags: Теги/категории (обязательный)
        permission: Группа с доступом к tool
        react_role: Роль в ReAct (standard, reason, exit)
        cost: Стоимость использования tool (для биллинга)
        billing_name: Имя для биллинга (по умолчанию = name)
        free_for_plans: Список тарифов с бесплатным доступом
        tariff_limits: Лимиты использования по тарифам
        parameters_model: Pydantic-модель аргументов — JSON Schema для LLM (`Field(description=...)`)
            и `model_validate` перед вызовом функции.
        listed_in_platform_tool_docs: участие в разделе platform tools у `/code/completions` и markdown-документации.

    Использование:
        @tool(
            name="calculator",
            description="Вычисляет математические выражения",
            tags=["math"],
            cost=0.1,
            billing_name="math_calculator"
        )
        async def calculator(expression: str, state: dict = None) -> str:
            import math
            result = eval(expression, {'__builtins__': {}}, {'sin': math.sin})
            return f"Результат: {result}"
    """

    def decorator(func: F) -> FunctionTool:
        tool_cls: type[FunctionTool] = FunctionTool
        if not listed_in_platform_tool_docs:
            safe = re.sub(r"[^0-9a-zA-Z_]", "_", name).strip("_") or "tool"
            tool_cls = type(
                f"_FunctionTool_{safe}",
                (FunctionTool,),
                {"listed_in_platform_tool_docs": False},
            )
        return tool_cls(
            func=func,
            name=name,
            description=description,
            tags=tags,
            permission=permission,
            react_role=react_role,
            cost=cost,
            billing_name=billing_name,
            free_for_plans=free_for_plans,
            tariff_limits=tariff_limits,
            parameters_model=parameters_model,
        )

    return decorator
