"""
BaseTool - базовый класс для инструментов.

Zero-Guess: все tools принимают ExecutionState вместо Dict.

Permissions:
- Каждый tool может иметь permission (группы с доступом)
- При отсутствии прав возвращается строка агенту (не exception)
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Mapping
from typing import TYPE_CHECKING, ClassVar, Protocol, TypeAlias, override

from pydantic import BaseModel

from apps.flows.config import get_settings
from apps.flows.src.clients.external_api_client import ExternalAPIClient
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.models.external_api import ExternalAPIConfig, HTTPMethod
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools.json_schema_parameters import pydantic_model_to_parameters_schema
from core.auth import permission_checker
from core.logging import get_logger
from core.state import parse_interrupt_body_from_external_dict
from core.types import JsonObject, JsonValue, require_json_object, require_json_value


def sanitize_tool_name(name: str) -> str:
    """
    Санитизирует имя tool для совместимости с OpenAI API.

    OpenAI требует pattern: ^[a-zA-Z0-9_-]+$
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_-")

    if not sanitized:
        sanitized = f"tool_{hashlib.md5(name.encode()).hexdigest()[:8]}"

    return sanitized


if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)

# Тип для permission: строка или список строк
Permission = str | list[str] | None
ToolArguments: TypeAlias = JsonObject
ToolResult: TypeAlias = JsonValue
ToolFunctionResult: TypeAlias = ToolResult | Awaitable[ToolResult]
ToolParametersSchema: TypeAlias = JsonObject
OpenAIToolSchema: TypeAlias = JsonObject


class ToolContainerRef(Protocol):
    pass


class BaseTool(ABC):
    """
    Базовый класс для всех инструментов.

    Определение параметров:
        - parameters_model: Pydantic модель для автогенерации JSON Schema
        - parameters: JSON Schema для ручного задания схемы в наследниках

    Permissions:
        - permission: группы с доступом к tool
        - При отсутствии прав возвращается строка агенту

    listed_in_platform_tool_docs:
        Участвует ли класс в разделе platform tools у /code/completions и /code/documentation
        (процессный ToolRegistry после register_builtin_tools).
    """

    listed_in_platform_tool_docs: ClassVar[bool] = True

    name: str = "base_tool"
    description: str = "Базовый инструмент"
    parameters_model: type[BaseModel] | None = None
    permission: Permission = None
    tags: list[str] = []  # Группы/категории: misc, math, docs, api, validation
    react_role: ReactToolRole = ReactToolRole.STANDARD
    container: ToolContainerRef | None = None
    is_nested_flow_tool: bool = False

    def get_tags(self) -> list[str]:
        """Возвращает теги/группы тула."""
        return self.tags if self.tags else ["misc"]

    @property
    def parameters(self) -> ToolParametersSchema:
        """Генерирует JSON Schema из parameters_model или возвращает пустой объект."""
        if self.parameters_model:
            return pydantic_model_to_parameters_schema(self.parameters_model)
        return {"type": "object", "properties": {}, "required": []}

    def _get_user_groups_from_state(self, state: "ExecutionState") -> list[str]:
        """
        Извлекает группы пользователя из state.

        Аргументы:
            state: ExecutionState агента

        Возвращает:
            Список групп пользователя
        """
        if state.user_groups:
            return state.user_groups

        extra = state.json_extra()
        raw_user = extra.get("user")
        if isinstance(raw_user, Mapping):
            user = require_json_object(raw_user, "state.user")
            raw_groups = user.get("grps")
            if isinstance(raw_groups, list) and all(isinstance(group, str) for group in raw_groups):
                return [group for group in raw_groups if isinstance(group, str)]

        return []

    def _check_permission(self, state: "ExecutionState") -> str | None:
        """
        Проверяет permission на tool.

        Аргументы:
            state: ExecutionState агента с информацией о пользователе

        Возвращает:
            None если есть доступ, иначе сообщение об ошибке для агента
        """
        config = get_settings()

        if not config.auth.permissions_enabled:
            return None
        if self.permission == []:
            return None

        user_groups = self._get_user_groups_from_state(state)

        if not permission_checker.check_tool_permission(user_groups, self.permission):
            required = permission_checker.normalize(self.permission)
            return (
                f"У пользователя нет прав на использование инструмента '{self.name}'. "
                f"Требуется одна из групп: {', '.join(required)}"
            )

        return None

    async def run(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """
        Единственная точка входа для выполнения tool.

        Наследники переопределяют этот метод.
        Для стандартных проверок permissions вызывайте _check_before_run().

        Аргументы:
            args: Аргументы вызова
            state: ExecutionState агента

        Возвращает:
            Результат выполнения
        """
        check_result = await self._check_before_run(args, state)
        if check_result is not None:
            return check_result

        return require_json_value(
            await self._run_impl(args, state),
            f"tool.{self.name}.result",
        )

    async def _check_before_run(
        self, args: ToolArguments, state: "ExecutionState"
    ) -> ToolResult | None:
        """
        Проверки перед выполнением: permissions.

        Возвращает:
            Результат если нужно вернуть permission error, None если продолжить
        """
        _ = args
        permission_error = self._check_permission(state)
        if permission_error:
            logger.warning(f"Tool {self.name}: permission denied")
            return permission_error

        return None

    @abstractmethod
    async def _run_impl(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """
        Реальное выполнение инструмента.

        Наследники реализуют логику тула здесь.

        Аргументы:
            args: Аргументы вызова
            state: ExecutionState агента

        Возвращает:
            Результат выполнения
        """
        pass

    def to_openai_schema(self) -> OpenAIToolSchema:
        """
        Возвращает схему инструмента для OpenAI.

        Возвращает:
            схема tool OpenAI
        """
        schema: OpenAIToolSchema = {
            "type": "function",
            "function": {
                "name": sanitize_tool_name(self.name),
                "description": self.description,
                "parameters": self.parameters,
            },
        }
        return schema

    @override
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"


class ExternalAPITool(BaseTool):
    """
    Инструмент для вызова внешнего HTTP API.

    Используется в основном в тестах; конфиг узла задаёт URL, headers, body_template (@state:, @var:).
    Схема аргументов для LLM — через canonical parameters_schema.
    """

    def __init__(
        self,
        api_id: str,
        url: str,
        method: str = "POST",
        title: str | None = None,
        description: str | None = None,
        headers: dict[str, str] | None = None,
        body_template: str = "{}",
        timeout: float = 30.0,
        response_mapping: dict[str, str] | None = None,
        permission: Permission = None,
        tags: list[str] | None = None,
        react_role: ReactToolRole = ReactToolRole.STANDARD,
        *,
        parameters_schema: JsonObject,
    ):
        self.api_id: str = api_id
        self.name: str = api_id
        self.description: str = description or f"External API: {api_id}"
        self.permission: Permission = permission
        self.tags: list[str] = tags or ["api"]
        self.react_role: ReactToolRole = react_role
        self._url: str = url
        self._method: str = method
        self._headers: dict[str, str] = headers or {}
        self._body_template: str = body_template
        self._timeout: float = timeout
        self._response_mapping: dict[str, str] = response_mapping or {}
        schema_obj = require_json_object(
            parameters_schema,
            f"ExternalAPITool.{api_id}.parameters_schema",
        )
        if schema_obj.get("type") != "object" or not isinstance(schema_obj.get("properties"), dict):
            raise ValueError(
                f"ExternalAPITool '{api_id}' parameters_schema must be object JSON Schema"
            )
        self._parameters_schema: ToolParametersSchema = schema_obj

    @property
    @override
    def parameters(self) -> ToolParametersSchema:
        """JSON Schema параметров внешнего API tool."""
        return self._parameters_schema

    @override
    async def _run_impl(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """Вызывает внешний API."""
        api_config = ExternalAPIConfig(
            api_id=self.api_id,
            name=self.name,
            description=self.description,
            url=self._url,
            method=HTTPMethod(self._method),
            headers=self._headers,
            body_template=self._body_template,
            timeout=self._timeout,
        )

        variables = state.variables

        client = ExternalAPIClient(timeout=self._timeout)
        result = require_json_object(
            await client.call(api_config, args, variables, state),
            f"external_api.{self.api_id}.response",
        )

        if result.get("status") == "waiting_input" and result.get("interrupt"):
            raw = result["interrupt"]
            if not isinstance(raw, dict):
                raise ValueError(
                    f"External API tool: interrupt должен быть dict, получено {type(raw)}"
                )
            body = parse_interrupt_body_from_external_dict(raw)
            raise FlowInterrupt(body=body)

        if result.get("status") == "error":
            raise ValueError(f"External API error: {result.get('error')}")

        data = result.get("data", {})

        for response_field, output_name in self._response_mapping.items():
            if isinstance(data, dict) and response_field in data:
                return require_json_value(
                    {output_name: data[response_field]},
                    f"external_api.{self.api_id}.mapped_response",
                )

        return require_json_value(data, f"external_api.{self.api_id}.data")
