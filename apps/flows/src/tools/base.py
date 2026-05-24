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
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, ClassVar, TypeAlias, override

from pydantic import BaseModel

from apps.flows.config import get_settings
from apps.flows.src.clients.external_api_client import ExternalAPIClient
from apps.flows.src.mock.resolver import get_mock_for_tool
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.models.external_api import ExternalAPIConfig, HTTPMethod
from apps.flows.src.runtime.exceptions import FlowInterrupt
from core.auth import permission_checker
from core.config.testing import is_testing
from core.logging import get_logger
from core.state import parse_interrupt_body_from_external_dict
from core.types import JsonArray, JsonObject, JsonValue, require_json_object, require_json_value


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
ToolMockResponse: TypeAlias = ToolResult | Callable[..., ToolFunctionResult]
ToolParametersSchema: TypeAlias = JsonObject
OpenAIToolSchema: TypeAlias = JsonObject


def _external_api_flat_args_schema_to_parameters_schema(
    schema: Mapping[str, JsonValue],
) -> ToolParametersSchema:
    """Плоский {name: {type, description, default?}} -> JSON Schema параметров tool."""
    properties: JsonObject = {}
    required: JsonArray = []

    for name, raw_meta in schema.items():
        if not isinstance(raw_meta, dict):
            raise ValueError(
                f"ExternalAPITool args_schema['{name}'] must be a dict, got {type(raw_meta).__name__}"
            )
        meta = require_json_object(raw_meta, f"ExternalAPITool args_schema.{name}")
        raw_type = meta.get("type", "string")
        if not isinstance(raw_type, str):
            raise ValueError(f"ExternalAPITool args_schema['{name}'].type must be a string")
        if raw_type not in {"string", "integer", "number", "boolean", "array", "object"}:
            raise ValueError(
                f"ExternalAPITool args_schema['{name}'].type has unsupported value: {raw_type}"
            )
        raw_description = meta.get("description", "")
        if not isinstance(raw_description, str):
            raise ValueError(
                f"ExternalAPITool args_schema['{name}'].description must be a string"
            )

        entry: JsonObject = {"type": raw_type, "description": raw_description}
        if "default" in meta:
            entry["default"] = meta["default"]
        else:
            required.append(name)
        properties[name] = entry

    return {"type": "object", "properties": properties, "required": required}


def is_test_mode() -> bool:
    """Проверяет запущены ли тесты."""
    return is_testing()


class BaseTool(ABC):
    """
    Базовый класс для всех инструментов.

    Определение параметров:
        - args_schema: Pydantic модель для автогенерации схемы (рекомендуется)
        - parameters: Dict для ручного задания схемы (для тулов из поля code в конфиге)

    Mock режим:
        - Определить mock_response для простых случаев
        - Или переопределить execute_mock() для сложной логики
        - В тестах (TESTING=true) вызывается execute_mock()

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
    args_schema: type[BaseModel] | None = None
    permission: Permission = None
    tags: list[str] = []  # Группы/категории: misc, math, docs, api, validation
    react_role: ReactToolRole = ReactToolRole.STANDARD

    # Mock ответ для тестов (переопределить в наследниках)
    mock_response: ToolMockResponse | None = "mock_result"

    def get_tags(self) -> list[str]:
        """Возвращает теги/группы тула."""
        return self.tags if self.tags else ["misc"]

    @property
    def parameters(self) -> ToolParametersSchema:
        """Генерирует JSON схему из args_schema или возвращает пустую."""
        if self.args_schema:
            schema = require_json_object(
                self.args_schema.model_json_schema(),
                f"{self.__class__.__name__}.args_schema",
            )
            _ = schema.pop("title", None)
            return schema
        return {"type": "object", "properties": {}, "required": []}

    def _has_custom_mock(self) -> bool:
        """Проверяет переопределён ли execute_mock в наследнике."""
        return type(self).execute_mock is not BaseTool.execute_mock

    def _get_user_groups_from_state(self, state: "ExecutionState") -> list[str]:
        """
        Извлекает группы пользователя из state.

        Args:
            state: ExecutionState агента

        Returns:
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

        Args:
            state: ExecutionState агента с информацией о пользователе

        Returns:
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
        Для стандартных проверок (permissions, mock) вызывайте _check_before_run().

        Args:
            args: Аргументы вызова
            state: ExecutionState агента

        Returns:
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
        Проверки перед выполнением: permissions, mock.

        Returns:
            Результат если нужно вернуть (permission error, mock), None если продолжить
        """
        permission_error = self._check_permission(state)
        if permission_error:
            logger.warning(f"Tool {self.name}: permission denied")
            return permission_error

        mock_result = get_mock_for_tool(state, self.name)
        if mock_result is not None:
            logger.debug(f"Tool {self.name}: using mock from state")
            return require_json_value(mock_result, f"mock.tools.{self.name}")

        if is_test_mode() and self._has_custom_mock():
            logger.debug(f"Tool {self.name}: mock mode (TESTING env)")
            return await self.execute_mock(args, state)

        return None

    @abstractmethod
    async def _run_impl(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """
        Реальное выполнение инструмента.

        Наследники реализуют логику тула здесь.

        Args:
            args: Аргументы вызова
            state: ExecutionState агента

        Returns:
            Результат выполнения
        """
        pass

    async def execute_mock(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """
        Mock выполнение для тестов.

        Args:
            args: Аргументы вызова
            state: ExecutionState агента

        Returns:
            Mock результат
        """
        _ = args
        _ = state
        if callable(self.mock_response):
            raise TypeError("BaseTool mock_response must be a JSON value")
        return require_json_value(self.mock_response, f"tool.{self.name}.mock_response")

    def to_openai_schema(self) -> OpenAIToolSchema:
        """
        Возвращает схему инструмента для OpenAI.

        Returns:
            OpenAI tool schema
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
    Схема аргументов для LLM — через args_schema родителя (по умолчанию без полей в properties).
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
        flat_args_schema: JsonObject | None = None,
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
        self._parameters_schema: ToolParametersSchema = (
            _external_api_flat_args_schema_to_parameters_schema(flat_args_schema)
            if flat_args_schema
            else {"type": "object", "properties": {}, "required": []}
        )

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

    @override
    async def execute_mock(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """Mock - возвращает пустой успешный ответ."""
        return {"status": "completed", "data": {}}
