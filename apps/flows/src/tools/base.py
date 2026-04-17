"""
BaseTool - базовый класс для инструментов.

Zero-Guess: все tools принимают ExecutionState вместо Dict.

Permissions:
- Каждый tool может иметь permission (группы с доступом)
- При отсутствии прав возвращается строка агенту (не exception)
"""

from __future__ import annotations

import copy
import hashlib
import os
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Type, Union

from pydantic import BaseModel

from apps.flows.src.models.enums import ReactToolRole


def sanitize_tool_name(name: str) -> str:
    """
    Санитизирует имя tool для совместимости с OpenAI API.
    
    OpenAI требует pattern: ^[a-zA-Z0-9_-]+$
    """
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_-')
    
    if not sanitized:
        sanitized = f"tool_{hashlib.md5(name.encode()).hexdigest()[:8]}"
    
    return sanitized

if TYPE_CHECKING:
    from core.state import ExecutionState
    from apps.flows.src.runtime.exceptions import FlowInterrupt

from apps.flows.src.clients.external_api_client import ExternalAPIClient
from apps.flows.config import get_settings
from apps.flows.src.container import get_container
from core.auth import permission_checker
from core.logging import get_logger
from apps.flows.src.mock import get_mock_for_tool
from apps.flows.src.models.external_api import ExternalAPIConfig, ParameterSchema

logger = get_logger(__name__)

# Тип для permission: строка или список строк
Permission = Optional[Union[str, List[str]]]


def is_test_mode() -> bool:
    """Проверяет запущены ли тесты."""
    from core.config.testing import is_testing
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
    args_schema: Optional[Type[BaseModel]] = None
    permission: Permission = None
    tags: List[str] = []  # Группы/категории: misc, math, docs, api, validation
    react_role: ReactToolRole = ReactToolRole.STANDARD

    # Mock ответ для тестов (переопределить в наследниках)
    mock_response: Any = "mock_result"

    def get_tags(self) -> List[str]:
        """Возвращает теги/группы тула."""
        return self.tags if self.tags else ["misc"]

    @property
    def parameters(self) -> Dict[str, Any]:
        """Генерирует JSON схему из args_schema или возвращает пустую."""
        if self.args_schema:
            schema = self.args_schema.model_json_schema()
            schema.pop("title", None)
            return schema
        return {"type": "object", "properties": {}, "required": []}

    def _has_custom_mock(self) -> bool:
        """Проверяет переопределён ли execute_mock в наследнике."""
        return type(self).execute_mock is not BaseTool.execute_mock

    def _get_user_groups_from_state(self, state: "ExecutionState") -> List[str]:
        """
        Извлекает группы пользователя из state.
        
        Args:
            state: ExecutionState агента
            
        Returns:
            Список групп пользователя
        """
        if state.user_groups:
            return state.user_groups
        
        user = getattr(state, "user", None)
        if isinstance(user, dict) and "grps" in user:
            return user["grps"]
        
        return []

    def _check_permission(self, state: "ExecutionState") -> Optional[str]:
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
        
        user_groups = self._get_user_groups_from_state(state)
        
        if not permission_checker.check_tool_permission(user_groups, self.permission):
            required = permission_checker.normalize(self.permission)
            return (
                f"У пользователя нет прав на использование инструмента '{self.name}'. "
                f"Требуется одна из групп: {', '.join(required)}"
            )
        
        return None

    async def run(self, args: Dict[str, Any], state: "ExecutionState") -> Any:
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
        
        return await self._run_impl(args, state)

    async def _check_before_run(
        self, args: Dict[str, Any], state: "ExecutionState"
    ) -> Optional[Any]:
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
            return mock_result
        
        if is_test_mode() and self._has_custom_mock():
            logger.debug(f"Tool {self.name}: mock mode (TESTING env)")
            return await self.execute_mock(args, state)

        return None

    @abstractmethod
    async def _run_impl(self, args: Dict[str, Any], state: "ExecutionState") -> Any:
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

    async def execute_mock(
        self, args: Dict[str, Any], state: "ExecutionState"
    ) -> Any:
        """
        Mock выполнение для тестов.

        Args:
            args: Аргументы вызова
            state: ExecutionState агента

        Returns:
            Mock результат
        """
        return self.mock_response

    def to_openai_schema(self) -> Dict[str, Any]:
        """
        Возвращает схему инструмента для OpenAI.

        Returns:
            OpenAI tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": sanitize_tool_name(self.name),
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"


class CodeTool(BaseTool):
    """
    Тул из Python-кода в конфиге (поле code).
    Выполнение через SafeEval.execute_tool.

    Не кладётся в процессный ToolRegistry.register и не показывается в platform tools документации:
    экземпляры живут только в списке tools конкретной llm_node (materialize).
    """

    listed_in_platform_tool_docs: ClassVar[bool] = False

    def __init__(
        self,
        tool_id: str,
        code: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        parameters_schema: Optional[Dict[str, Any]] = None,
        permission: Permission = None,
        tags: Optional[List[str]] = None,
        react_role: ReactToolRole = ReactToolRole.STANDARD,
        resources: Optional[Dict[str, Any]] = None,
    ):
        self.name = tool_id
        self.description = description or f"Code tool: {tool_id}"
        self.permission = permission
        self.tags = tags or ["misc"]
        self.react_role = react_role
        self._code = code
        self._resources_config = resources or {}

        if parameters_schema is not None:
            if not isinstance(parameters_schema, dict):
                raise ValueError(f"CodeTool '{tool_id}': parameters_schema must be a dict")
            if parameters_schema.get("type") != "object":
                raise ValueError(
                    f"CodeTool '{tool_id}': parameters_schema must have type: object"
                )
            props = parameters_schema.get("properties")
            if not isinstance(props, dict):
                raise ValueError(
                    f"CodeTool '{tool_id}': parameters_schema must contain object properties"
                )
            self._parameters = copy.deepcopy(parameters_schema)
        elif parameters:
            props = {}
            required = []
            for param_name, param_info in parameters.items():
                props[param_name] = {
                    "type": param_info.type
                    if hasattr(param_info, "type")
                    else param_info.get("type", "string"),
                    "description": param_info.description
                    if hasattr(param_info, "description")
                    else param_info.get("description", ""),
                }
                is_req = (
                    param_info.required
                    if hasattr(param_info, "required")
                    else param_info.get("required", True)
                )
                if is_req:
                    required.append(param_name)
            self._parameters = {"type": "object", "properties": props, "required": required}
        else:
            self._parameters = None

    @property
    def parameters(self) -> Dict[str, Any]:
        """Возвращает параметры."""
        if self._parameters:
            return self._parameters
        return {"type": "object", "properties": {}, "required": []}

    async def _run_impl(self, args: Dict[str, Any], state: "ExecutionState") -> Any:
        """Выполняет inline код через SafeEval."""
        full_args = self._apply_defaults(args)
        
        variables = state.variables
        
        # Резолвим resources из конфига tool
        resources = await self._resolve_resources(state)
        
        SafeEval = get_container().safe_eval_class
        evaluator = SafeEval(variables=variables, resources=resources)
        
        result = await evaluator.execute_tool(self._code, full_args, state)
        
        return result
    
    def _apply_defaults(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Применяет default значения из args_schema к args."""
        if not self._parameters:
            return args
        
        result = dict(args)
        properties = self._parameters.get("properties", {})
        
        for prop_name, prop_schema in properties.items():
            if prop_name not in result and "default" in prop_schema:
                result[prop_name] = prop_schema["default"]
        
        return result

    async def _resolve_resources(self, state: "ExecutionState") -> Dict[str, Any]:
        """
        Резолвит resources для tool.
        
        Единообразно с нодами — иерархия flow > skill > tool.
        """
        container = get_container()
        
        flow_resources, skill_resources = await container.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.skill_id,
            state.flow_config_version,
        )
        
        # Ресурсы tool
        tool_resources = self._resources_config
        
        if not flow_resources and not skill_resources and not tool_resources:
            return {}
        
        return await container.resource_resolver.resolve_for_node(
            flow_resources=flow_resources,
            skill_resources=skill_resources,
            node_resources=tool_resources,
            variables=state.variables,
        )


class ExternalAPITool(BaseTool):
    """
    Инструмент для вызова внешнего HTTP API.

    Может использоваться в react агентах для вызова внешних сервисов.
    Поддерживает @var: переменные и OpenAPI-like параметры.
    """

    def __init__(
        self,
        api_id: str,
        url: str,
        method: str = "POST",
        title: Optional[str] = None,
        description: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_headers: Optional[Dict[str, str]] = None,
        parameters: Optional[list] = None,
        timeout: float = 30.0,
        response_mapping: Optional[Dict[str, str]] = None,
        permission: Permission = None,
        tags: Optional[List[str]] = None,
        react_role: ReactToolRole = ReactToolRole.STANDARD,
    ):
        self.api_id = api_id
        self.name = api_id
        self.description = description or f"External API: {api_id}"
        self.permission = permission
        self.tags = tags or ["api"]
        self.react_role = react_role
        self._url = url
        self._method = method
        self._headers = headers or {}
        self._auth_headers = auth_headers or {}
        self._api_parameters = parameters or []
        self._timeout = timeout
        self._response_mapping = response_mapping or {}

    @property
    def parameters(self) -> Dict[str, Any]:
        """Строит OpenAI-совместимую схему параметров."""
        properties = {}
        required = []

        for param in self._api_parameters:
            param_name = param.get("name") if isinstance(param, dict) else param.name
            param_type = (
                param.get("type", "string")
                if isinstance(param, dict)
                else getattr(param, "type", "string")
            )
            param_desc = (
                param.get("description")
                if isinstance(param, dict)
                else getattr(param, "description", None)
            )
            param_required = (
                param.get("required", False)
                if isinstance(param, dict)
                else getattr(param, "required", False)
            )

            properties[param_name] = {"type": param_type}
            if param_desc:
                properties[param_name]["description"] = param_desc

            if param_required:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    async def _run_impl(self, args: Dict[str, Any], state: "ExecutionState") -> Any:
        """Вызывает внешний API."""
        parameters = []
        for p in self._api_parameters:
            if isinstance(p, dict):
                parameters.append(ParameterSchema(**p))
            else:
                parameters.append(p)

        api_config = ExternalAPIConfig(
            api_id=self.api_id,
            name=self.name,
            description=self.description,
            url=self._url,
            method=self._method,
            headers=self._headers,
            auth_headers=self._auth_headers,
            parameters=parameters,
            timeout=self._timeout,
        )

        variables = state.variables

        client = ExternalAPIClient(timeout=self._timeout)
        result = await client.call(api_config, args, variables)

        if result.get("status") == "waiting_input" and result.get("interrupt"):
            from apps.flows.src.runtime.exceptions import FlowInterrupt
            from core.state import parse_interrupt_body_from_external_dict

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
                return {output_name: data[response_field]}

        return data

    async def execute_mock(self, args: Dict[str, Any], state: "ExecutionState") -> Any:
        """Mock - возвращает пустой успешный ответ."""
        return {"status": "completed", "data": {}}
