"""
Декоратор @tool для создания tools из функций.

Zero-Guess: все tools принимают ExecutionState.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

from pydantic import BaseModel

from apps.flows.src.mock import get_mock_for_tool
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.models.tool_reference import CallParameter
from apps.flows.src.tools.base import BaseTool
from core.config.testing import is_testing
from core.logging import get_logger

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)
Permission = str | list[str] | None

F = TypeVar("F", bound=Callable[..., Any])


def is_test_mode() -> bool:
    """Проверяет запущены ли тесты."""
    return is_testing()


class FunctionTool(BaseTool):
    """
    Tool созданный из функции через декоратор @tool.

    Хранит ссылку на оригинальную функцию для извлечения кода.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        name: str,
        description: str,
        tags: list[str],
        mock_response: Any = None,
        permission: Permission = None,
        react_role: ReactToolRole = ReactToolRole.STANDARD,
        cost: float = 0.0,
        billing_name: str | None = None,
        free_for_plans: list[str] | None = None,
        tariff_limits: dict[str, int] | None = None,
        args_schema: type[BaseModel] | None = None,
    ):
        self._func = func
        self.name = name
        self.description = description
        self.tags = tags
        self._mock_response = mock_response
        self.permission = permission
        self.react_role = react_role
        self.args_schema = args_schema
        self._parameters = {} if args_schema is not None else self._extract_parameters(func)

        self.cost = cost
        self.billing_name = billing_name or name
        self.free_for_plans = free_for_plans or []
        self.tariff_limits = tariff_limits or {}

    def _extract_parameters(self, func: Callable[..., Any]) -> dict[str, CallParameter]:
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
    def parameters(self) -> dict[str, Any]:
        """JSON схема параметров для LLM."""
        if self.args_schema is not None:
            schema = self.args_schema.model_json_schema()
            schema.pop("title", None)
            return schema

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

    async def run(self, args: dict[str, Any], state: "ExecutionState") -> Any:
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
                sig = inspect.signature(self._mock_response)
                if "state" in sig.parameters:
                    result = self._mock_response(args, state=state)
                else:
                    result = self._mock_response(args)
                if inspect.iscoroutine(result):
                    return await result
                return result
            return self._mock_response

        logger.debug(f"Tool {self.name}: real mode")
        return await self._run_impl(args, state)

    async def _run_impl(self, args: dict[str, Any], state: "ExecutionState") -> Any:
        """Выполняет функцию. State передается как ExecutionState."""
        sig = inspect.signature(self._func)
        if self.args_schema is not None:
            validated = self.args_schema.model_validate(args)
            call_kw = validated.model_dump()
        else:
            call_kw = dict(args)

        if "state" in sig.parameters:
            if inspect.iscoroutinefunction(self._func):
                result = await self._func(**call_kw, state=state)
            else:
                result = self._func(**call_kw, state=state)
            return result

        if inspect.iscoroutinefunction(self._func):
            return await self._func(**call_kw)
        return self._func(**call_kw)

    def get_source_code(self) -> str:
        """Возвращает исходный код функции."""
        return inspect.getsource(self._func)

    @property
    def call_parameters(self) -> dict[str, CallParameter]:
        """Параметры вызова, извлечённые из сигнатуры функции."""
        return dict(self._parameters)

    @property
    def mock_response(self) -> Any:
        """Mock-ответ, заданный в декораторе tool."""
        return self._mock_response


def tool(
    name: str,
    description: str,
    tags: list[str],
    mock_response: Any = None,
    permission: Permission = None,
    react_role: ReactToolRole = ReactToolRole.STANDARD,
    cost: float = 0.0,
    billing_name: str | None = None,
    free_for_plans: list[str] | None = None,
    tariff_limits: dict[str, int] | None = None,
    args_schema: type[BaseModel] | None = None,
    listed_in_platform_tool_docs: bool = True,
) -> Callable[[F], FunctionTool]:
    """
    Декоратор для создания tool из функции.

    Args:
        name: Имя tool (обязательный)
        description: Описание для LLM (обязательный)
        tags: Теги/категории (обязательный)
        mock_response: Mock ответ - строка, dict или callable
        permission: Группа с доступом к tool
        react_role: Роль в ReAct (standard, reason, exit)
        cost: Стоимость использования tool (для биллинга)
        billing_name: Имя для биллинга (по умолчанию = name)
        free_for_plans: Список тарифов с бесплатным доступом
        tariff_limits: Лимиты использования по тарифам
        args_schema: Pydantic-модель аргументов — JSON Schema для LLM (`Field(description=...)`)
            и `model_validate` перед вызовом функции; без схемы — разбор сигнатуры как раньше.
        listed_in_platform_tool_docs: участие в разделе platform tools у `/code/completions` и markdown-документации.

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
            mock_response=mock_response,
            permission=permission,
            react_role=react_role,
            cost=cost,
            billing_name=billing_name,
            free_for_plans=free_for_plans,
            tariff_limits=tariff_limits,
            args_schema=args_schema,
        )
    return decorator
