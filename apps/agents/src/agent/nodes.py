"""
Ноды для Agent.

Нода = функция ExecutionState -> ExecutionState.
Маршрутизация через edges в Agent, не в нодах.

Типы нод:
- ReactNode - LLM нода с ReAct циклом
- FunctionNode - Python функция (inline код)
- ToolNode - BaseTool как нода графа
- AgentNode - вложенный agent
- RemoteAgentNode - внешний агент по A2A протоколу
- ExternalAPINode - вызов внешнего HTTP API
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from apps.agents.src.agent.exceptions import AgentInterrupt
from apps.agents.src.agent.runners import ReactNodeRunner
from apps.agents.src.clients.external_api_client import ExternalAPIClient
from core.clients.llm import get_llm
from apps.agents.src.container import get_container
from apps.agents.src.mapping import MappingResolver
from apps.agents.src.mock import get_mock_for_node
from apps.agents.src.models import NodeLLMOverride, NodeConfig, ReactConfig
from apps.agents.src.models.enums import NodeType
from apps.agents.src.models.external_api import ExternalAPIConfig, ParameterSchema
from apps.agents.src.models.tool_reference import CallParameter
from core.state import ExecutionState, InterruptData
from apps.agents.src.tools.base import BaseTool, InlineTool
from core.logging import get_logger
from core.errors import ResourceNotFoundError

logger = get_logger(__name__)


class BaseNode(ABC):
    """Базовый класс для нод. Node = функция ExecutionState -> ExecutionState."""

    name: str = "node"
    description: Optional[str] = None

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        self.node_id = node_id
        self.config = config or {}

    @classmethod
    def from_config(cls, node_id: str, config: Dict[str, Any]) -> "BaseNode":
        """Создает ноду из конфига."""
        return cls(node_id=node_id, config=config)

    def _ensure_state(self, state: Any) -> ExecutionState:
        """Проверяет что state это ExecutionState."""
        if isinstance(state, ExecutionState):
            return state
        raise TypeError(
            f"state must be ExecutionState, got {type(state).__name__}. "
            "Use ExecutionState or ExecutionState.model_validate() to convert dict."
        )

    def _check_mock(self, state: ExecutionState) -> Optional[Dict[str, Any]]:
        """Проверяет наличие mock для ноды."""
        return get_mock_for_node(state, self.node_id)

    @abstractmethod
    async def run(self, state: ExecutionState) -> ExecutionState:
        """Выполняет ноду и возвращает обновленный state."""
        pass

    def as_tool(
        self, name: Optional[str] = None, description: Optional[str] = None
    ) -> "NodeAsTool":
        """
        Превращает ноду в tool для использования в других нодах.

        Args:
            name: Имя tool
            description: Описание tool

        Returns:
            NodeAsTool wrapper
        """
        return NodeAsTool(
            node=self,
            name=name or f"{self.node_id}_tool",
            description=description or self.description or f"Вызов ноды {self.node_id}",
        )


class ReactNode(BaseNode):
    """
    ReAct нода (LLM + tools).

    Объединяет функционал ноды графа и исполнителя.
    Может использоваться как базовый класс для кастомных нод.

    Атрибуты класса (для кастомных нод):
    - name: имя ноды
    - description: описание
    - prompt: системный промпт
    - tools: список tools

    Параметры конструктора (для ноды графа):
    - node_id: ID ноды в графе
    - prompt: шаблон промпта
    - tools: список inline tool configs
    - llm_config: конфигурация LLM
    - input_mapping: маппинг входных данных

    Хуки для кастомизации:
    - before_prompt_render: перед рендерингом промпта
    - after_prompt_render: после рендеринга промпта
    """

    # Атрибуты для кастомных классов
    name: str = "react_node"
    description: Optional[str] = None
    prompt: Optional[str] = None
    tools: List[Any] = []

    def __init__(
        self,
        node_id: Optional[str] = None,
        prompt: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        llm_config: Optional[Dict[str, Any]] = None,
        input_mapping: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        node_config: Optional[NodeConfig] = None,
    ):
        super().__init__(node_id or self.name, config)
        
        # Извлекаем параметры из config если они не переданы явно
        cfg = config or {}
        
        self.prompt_template = prompt or self.prompt or cfg.get("prompt", "")
        self.tool_refs = tools if tools is not None else cfg.get("tools", [])
        self.llm_config_dict = llm_config or cfg.get("llm", {})
        self.input_mapping = input_mapping or cfg.get("input_mapping")
        
        self._node_config = node_config
        self._runner = None
        self._loaded_tools: Optional[List[Any]] = None

    @property
    def react_node_id(self) -> str:
        """ID ноды"""
        if self._node_config:
            return self._node_config.node_id
        return self.node_id

    @property
    def llm_config(self) -> Dict[str, Any]:
        """LLM конфигурация."""
        return self.llm_config_dict

    @property
    def react_node_name(self) -> str:
        """Название ноды"""
        if self._node_config:
            return self._node_config.name
        return self.name

    @property
    def react_node_description(self) -> Optional[str]:
        """Описание ноды"""
        if self._node_config and self._node_config.description:
            return self._node_config.description
        return self.description

    @property
    def react_node_prompt(self) -> Optional[str]:
        """Промпт ноды"""
        if self._node_config and self._node_config.prompt:
            return self._node_config.prompt
        return self.prompt_template or self.prompt

    async def run(self, state: ExecutionState) -> ExecutionState:
        """Запускает ReactNode как ноду графа."""
        mock_data = self._check_mock(state)
        if mock_data is not None:
            logger.info(f"[node:{self.node_id}] using mock data")
            for key, value in mock_data.items():
                setattr(state, key, value)
            return state

        agent_state = self._build_agent_state(state)

        if self.tool_refs and self._loaded_tools is None:
            self._loaded_tools = await self._load_tools()

        logger.info(f"[node:{self.node_id}] Запуск ReactNode")

        content = agent_state.content or ""

        try:
            result = await self.ainvoke({"content": content}, agent_state)
        except AgentInterrupt:
            self._copy_state_back(agent_state, state)
            raise

        self._copy_state_back(result, state)
        return state

    def _copy_state_back(self, source: ExecutionState, target: ExecutionState) -> None:
        """Копирует все изменения из source обратно в target."""
        for field_name in ExecutionState.model_fields:
            if hasattr(source, field_name):
                setattr(target, field_name, getattr(source, field_name))
        
        if hasattr(source, '__pydantic_extra__') and source.__pydantic_extra__:
            if not hasattr(target, '__pydantic_extra__') or target.__pydantic_extra__ is None:
                target.__pydantic_extra__ = {}
            target.__pydantic_extra__.update(source.__pydantic_extra__)

    async def ainvoke(
        self, input_data: Dict[str, Any], state: ExecutionState
    ) -> ExecutionState:
        """
        Выполняет ReactNode.

        Args:
            input_data: Входные данные (content, etc)
            state: ExecutionState

        Returns:
            ExecutionState с результатом

        Raises:
            AgentInterrupt: Если ReactNode задает вопрос пользователю
        """
        runner = await self.get_runner()

        async for _ in runner.run(input_data, state):
            pass

        return state

    async def get_runner(self):
        """Возвращает runner для ReactNode."""
        if self._runner is not None:
            return self._runner

        tools = await self.get_tools()
        llm = self._get_llm()
        prompt = self.react_node_prompt or ""

        config = self._node_config or self._create_default_config()

        self._runner = ReactNodeRunner(
            node_config=config,
            tools=tools,
            llm=llm,
            prompt=prompt,
            react_node=self,
        )

        return self._runner

    async def get_tools(self) -> List[Any]:
        """Возвращает список tools."""
        if self._loaded_tools is not None:
            return self._loaded_tools
        
        # Загружаем tools из tool_refs если они есть
        if self.tool_refs:
            self._loaded_tools = await self._load_tools()
            return self._loaded_tools
        
        # Если нет tool_refs, возвращаем атрибут класса tools (для кастомных нод)
        # Атрибут класса tools должен содержать уже готовые объекты, не конфиги
        return self.tools

    async def set_tools(self, tools: List[Any]) -> None:
        """Устанавливает tools."""
        self._loaded_tools = tools

    def _get_llm(self):
        """Возвращает LLM клиент."""
        model = None
        temp = None

        if self._node_config and self._node_config.llm_override:
            model = self._node_config.llm_override.model
            temp = self._node_config.llm_override.temperature
        elif self.llm_config_dict:
            model = self.llm_config_dict.get("model")
            temp = self.llm_config_dict.get("temperature")

        logger.info(f"[_get_llm] node_id={self.node_id}, model={model}, temp={temp}, llm_config_dict={self.llm_config_dict}")
        return get_llm(model_name=model, temperature=temp)

    def _create_default_config(self) -> NodeConfig:
        """Создает конфигурацию по умолчанию."""
        llm_override = None
        if self.llm_config_dict:
            llm_override = NodeLLMOverride(
                model=self.llm_config_dict.get("model"),
                temperature=self.llm_config_dict.get("temperature"),
            )

        # Создаём ReactConfig из config dict если есть
        react_config = None
        react_dict = self.config.get("react") if self.config else None
        if react_dict:
            react_config = ReactConfig(**react_dict)
            
        return NodeConfig(
            node_id=self.node_id,
            type=NodeType.REACT_NODE,
            name=self.node_id,
            description=self.description or "",
            prompt=self.prompt_template or self.prompt or "",
            llm_override=llm_override,
            react=react_config,
        )

    def _build_agent_state(self, state: ExecutionState) -> ExecutionState:
        """Строит ExecutionState на основе input_mapping."""
        if not self.input_mapping:
            # Возвращаем копию состояния
            return ExecutionState.model_validate(state.model_dump(exclude_none=False))
        
        mapped_dict = MappingResolver.build_mapped_state(self.input_mapping, state)
        mapped_dict["task_id"] = state.task_id
        mapped_dict["context_id"] = state.context_id
        mapped_dict["user_id"] = state.user_id
        mapped_dict["session_id"] = state.session_id
        mapped_dict["variables"] = state.variables
        mapped_dict["mock"] = state.mock
        mapped_dict.setdefault("nested_states", state.nested_states or {})
        mapped_dict.setdefault("interrupted_path", state.interrupt_path or [])
        mapped_dict.setdefault("messages", state.messages or [])
        return ExecutionState(**mapped_dict)

    async def _load_tools(self) -> List[Any]:
        """Создаёт tools из inline конфигов."""
        container = get_container()
        return await container.tool_registry.create_tools(self.tool_refs)

    async def before_prompt_render(
        self, prompt_template: str, state: Dict[str, Any], variables: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """
        Хук вызывается ДО рендеринга промпта.
        Переопределите для модификации промпта и переменных.

        Args:
            prompt_template: Исходный шаблон промпта
            state: Текущее state
            variables: Переменные для рендеринга

        Returns:
            (modified_prompt_template, modified_variables)
        """
        return prompt_template, variables

    async def after_prompt_render(
        self, rendered_prompt: str, state: Dict[str, Any]
    ) -> str:
        """
        Хук вызывается ПОСЛЕ рендеринга промпта.
        Переопределите для модификации финального промпта.

        Args:
            rendered_prompt: Рендеренный промпт
            state: Текущий state

        Returns:
            Модифицированный промпт
        """
        return rendered_prompt

    def as_tool(
        self, name: Optional[str] = None, description: Optional[str] = None
    ) -> "NodeAsTool":
        """
        Превращает ReactNode в tool для использования в других нодах.

        Args:
            name: Имя tool
            description: Описание tool

        Returns:
            NodeAsTool wrapper
        """
        return NodeAsTool(
            node=self,
            name=name or f"{self.react_node_id}_tool",
            description=description or self.react_node_description or f"Вызов ноды {self.react_node_name}",
        )


class NodeAsTool:
    """Обертка для использования любой ноды как tool."""

    def __init__(self, node: "BaseNode", name: str, description: str):
        self.node = node
        self.name = name
        self.description = description
        self.parameters = {
            "type": "object",
            "properties": {"request": {"type": "string", "description": "Запрос к ноде"}},
            "required": ["request"],
        }

    async def execute(self, args: Dict[str, Any], state: Dict[str, Any]) -> str:
        """Выполняет ноду как tool."""
        request = args.get("request", "")
        node_name = getattr(self.node, "react_node_name", self.node.node_id)
        logger.info(f"NodeAsTool: вызов {node_name} с запросом: {request[:100]}")
        
        # Для ReactNode используем ainvoke
        if hasattr(self.node, "ainvoke"):
            input_data = {"content": request}
            result = await self.node.ainvoke(input_data, state)
            return result.get("response", "Нет ответа от ноды")
        
        # Для остальных нод используем run
        state["content"] = request
        result = await self.node.run(state)
        if isinstance(result, dict):
            return result.get("response", result.get("result", str(result)))
        return str(result)

    def to_openai_schema(self) -> Dict[str, Any]:
        """Возвращает схему для OpenAI."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class FunctionNode(BaseNode):
    """Python функция из inline кода или callable."""

    def __init__(
        self,
        node_id: str,
        code: Any = None,  # str (inline код) или callable (для тестов)
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(node_id, config)
        self._callable = None
        
        self.code = code
        cfg = config or {}
        
        if self.code is None:
            self.code = cfg.get("code")
            
        if self.code is None and cfg.get("function"):
            # Загрузка по пути к функции (CODE_REFERENCE)
            function_path = cfg["function"]
            try:
                module_path, func_name = function_path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                func = getattr(module, func_name)
                # Для callables сохраняем напрямую если передали путь
                if not self.code:
                    self.code = inspect.getsource(func)
                    self._callable = func
            except Exception as e:
                # Мягкое падение: если путь не валиден, ругнемся при run
                logger.error(f"Node '{node_id}': failed to load code from {function_path}: {e}")
        
        if callable(self.code):
            # Для тестов - принимаем callable напрямую
            self._callable = self.code
            self.code = None

    async def run(self, state: ExecutionState) -> ExecutionState:
        """Выполняет inline код через TaskIQ или callable напрямую."""
        mock_data = self._check_mock(state)
        if mock_data is not None:
            logger.info(f"[node:{self.node_id}] using mock data")
            for key, value in mock_data.items():
                setattr(state, key, value)
            return state

        if self._callable is not None:
            if asyncio.iscoroutinefunction(self._callable):
                result = await self._callable(state)
            else:
                result = self._callable(state)
            if isinstance(result, dict):
                return ExecutionState.model_validate(result)
            return result
        elif self.code:
            run_inline_code = get_container().run_inline_code
            result = await run_inline_code(self.code, state)
            if isinstance(result, dict):
                return ExecutionState.model_validate(result)
            return result
        else:
            raise ValueError(f"Node '{self.node_id}': code required")


class ToolNode(BaseNode):
    """Tool как нода графа."""

    def __init__(
        self,
        node_id: str,
        tool: Optional[BaseTool] = None,
        input_mapping: Optional[Dict[str, Any]] = None,
        output_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(node_id, config)
        self.tool = tool
        
        cfg = config or {}
        self.input_mapping = input_mapping if input_mapping is not None else (cfg.get("input_mapping") or {})
        self.output_key = output_key if output_key is not None else cfg.get("output_key", node_id)

    async def _ensure_tool(self):
        """Загружает tool если он еще не загружен."""
        if self.tool:
            return

        cfg = self.config
        code = cfg.get("code")
        tool_id = cfg.get("tool_id") or self.node_id
        
        if tool_id and not code:
            container = get_container()
            tool = await container.tool_registry.create_tool({"tool_id": tool_id})
            if tool is None:
                raise ValueError(f"Node '{self.node_id}': tool '{tool_id}' not found")
            self.tool = tool
            return
            
        if not code:
             raise ValueError(f"Node '{self.node_id}': code or tool_id required for type=tool")
             
        parameters = None
        args_schema = cfg.get("args_schema")
        logger.info(f"[ToolNode._ensure_tool] args_schema type: {type(args_schema)}, value: {args_schema}")
        if args_schema:
            try:
                parameters = {}
                logger.info(f"[ToolNode._ensure_tool] Iterating over args_schema.items()")
                for name, schema in args_schema.items():
                    logger.info(f"[ToolNode._ensure_tool] Processing param '{name}', schema type: {type(schema)}, value: {schema}")
                    parameters[name] = CallParameter(
                        type=schema.get("type", "string"),
                        description=schema.get("description", ""),
                    )
                logger.info(f"[ToolNode._ensure_tool] Successfully created parameters: {list(parameters.keys())}")
            except Exception as e:
                logger.error(f"[ToolNode._ensure_tool] Error creating parameters: {e}", exc_info=True)
                raise
        
        self.tool = InlineTool(
            tool_id=tool_id,
            code=code,
            description=cfg.get("description"),
            parameters=parameters,
        )

    async def run(self, state: ExecutionState) -> ExecutionState:
        """Выполняет tool."""
        mock_data = self._check_mock(state)
        if mock_data is not None:
            logger.info(f"[node:{self.node_id}] using mock data")
            for key, value in mock_data.items():
                setattr(state, key, value)
            return state

        await self._ensure_tool()

        args = self._build_args(state)
        logger.info(f"[node:{self.node_id}] Вызов tool '{self.tool.name}' с args: {list(args.keys())}")
        result = await self.tool.run(args, state)
        setattr(state, self.output_key, result)
        return state

    def _build_args(self, state: ExecutionState) -> Dict[str, Any]:
        """Собирает аргументы tool из state по маппингу."""
        args = {}
        if hasattr(self.tool, "parameters") and self.tool.parameters:
            properties = self.tool.parameters.get("properties", {})
            for prop_name, prop_schema in properties.items():
                if "default" in prop_schema:
                    args[prop_name] = prop_schema["default"]

        for arg_name, source in self.input_mapping.items():
            args[arg_name] = MappingResolver.resolve_value(source, state)

        return args


class AgentNode(BaseNode):
    """Вложенный Agent с поддержкой skill."""

    def __init__(
        self,
        node_id: str,
        agent_id: Optional[str] = None,
        skill_id: str = "default",
        input_mapping: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(node_id, config)
        cfg = config or {}
        
        self.agent_id = agent_id or cfg.get("agent_id")
        self.skill_id = skill_id or cfg.get("skill_id", "default")
        self.input_mapping = input_mapping or cfg.get("input_mapping")
        self._agent = None

    async def run(self, state: ExecutionState) -> ExecutionState:
        """Запускает вложенный Agent с указанным skill."""
        mock_data = self._check_mock(state)
        if mock_data is not None:
            logger.info(f"[node:{self.node_id}] using mock data")
            for key, value in mock_data.items():
                setattr(state, key, value)
            return state
            
        if not self.agent_id:
             raise ValueError(f"Node '{self.node_id}': agent_id required")

        nested_state = self._build_agent_state(state)

        if self._agent is None:
            container = get_container()
            self._agent = await container.agent_factory.get_flow(self.agent_id, self.skill_id)

        result = await self._agent.execute(nested_state)
        
        for field_name in ExecutionState.model_fields:
            if hasattr(result, field_name):
                setattr(state, field_name, getattr(result, field_name))
        
        if hasattr(result, '__pydantic_extra__') and result.__pydantic_extra__:
            if not hasattr(state, '__pydantic_extra__') or state.__pydantic_extra__ is None:
                state.__pydantic_extra__ = {}
            state.__pydantic_extra__.update(result.__pydantic_extra__)
        
        return state

    def _build_agent_state(self, state: ExecutionState) -> ExecutionState:
        """Строит ExecutionState для вложенного Agent."""
        if not self.input_mapping:
            # Возвращаем копию состояния
            return ExecutionState.model_validate(state.model_dump(exclude_none=False))
        
        mapped_dict = MappingResolver.build_mapped_state(self.input_mapping, state)
        return ExecutionState.create(
            task_id=state.task_id,
            context_id=state.context_id,
            user_id=state.user_id,
            session_id=state.session_id,
            variables=state.variables,
            **mapped_dict
        )


class RemoteAgentNode(BaseNode):
    """Внешний агент по A2A протоколу."""

    def __init__(
        self,
        node_id: str,
        url: Optional[str] = None,
        agent_id: Optional[str] = None,
        skill_id: Optional[str] = None,
        auth_headers: Optional[Dict[str, str]] = None,
        input_mapping: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(node_id, config)
        cfg = config or {}
        
        self.url = url if url is not None else cfg.get("url")
        self.agent_id = agent_id if agent_id is not None else cfg.get("agent_id")
        self.skill_id = skill_id if skill_id is not None else cfg.get("skill_id", "default")
        self.auth_headers_config = auth_headers if auth_headers is not None else cfg.get("auth_headers", {})
        self.input_mapping = input_mapping if input_mapping is not None else cfg.get("input_mapping", {"type": "content"})

        if not self.url and not self.agent_id:
            # Отложим проверку до run, так как config может быть не полным при инициализации
            pass

    async def run(self, state: ExecutionState) -> ExecutionState:
        """Вызывает внешнего агента."""
        mock_data = self._check_mock(state)
        if mock_data is not None:
            logger.info(f"[node:{self.node_id}] using mock data")
            for key, value in mock_data.items():
                setattr(state, key, value)
            return state
            
        if not self.url and not self.agent_id:
             raise ValueError("RemoteAgentNode requires 'url' or 'agent_id'")

        container = get_container()
        variables = state.variables

        url = self.url
        auth_headers: Dict[str, str] = {}

        if self.agent_id:
            agent = await container.agent_discovery.get_agent(self.agent_id)
            if agent is None:
                raise ValueError(f"External agent '{self.agent_id}' not found in registry")
            url = agent.url
            auth_headers = agent.auth_headers
        else:
            url = self._resolve_value(self.url, variables)
            auth_headers = self._resolve_auth_headers(self.auth_headers_config, variables)

        content = self._resolve_input(state)
        session_id = state.session_id

        result = await container.a2a_client.send_task(
            base_url=url,
            content=content,
            session_id=session_id,
            skill_id=self.skill_id,
            auth_headers=auth_headers,
        )

        state.response = result.get("response", "")
        setattr(state, "remote_status", result.get("status", "completed"))
        return state

    def _resolve_value(self, value: str, variables: Dict[str, Any]) -> str:
        """Резолвит @var: в строке."""
        if not value:
            return value
        return MappingResolver.resolve_vars_in_string(value, variables)

    def _resolve_auth_headers(
        self,
        headers: Optional[Dict[str, str]],
        variables: Dict[str, Any],
    ) -> Dict[str, str]:
        """Резолвит @var: во всех значениях headers."""
        if not headers:
            return {}
        return {k: self._resolve_value(v, variables) for k, v in headers.items()}

    def _resolve_input(self, state: ExecutionState) -> str:
        """Резолвит входные данные для отправки агенту."""
        mapping = self.input_mapping or {"type": "content"}

        if "type" not in mapping:
            mapped_state = MappingResolver.build_mapped_state(mapping, state)
            value = mapped_state.get("content", "")
            if isinstance(value, str):
                return value
            return json.dumps(value, ensure_ascii=False)

        mapping_type = mapping.get("type", "content")

        if mapping_type == "content":
            return getattr(state, "content", "")
        elif mapping_type == "state_field":
            field = mapping.get("field", "content")
            value = getattr(state, field, "")
            if isinstance(value, str):
                return value
            return json.dumps(value, ensure_ascii=False)
        elif mapping_type == "messages":
            last_n = mapping.get("last_n", 1)
            messages = state.messages or []
            if not messages:
                return state.get("content", "")
            selected = messages[-last_n:] if last_n > 0 else messages
            return self._format_messages(selected)

        return state.get("content", "")

    def _format_messages(self, messages: list) -> str:
        """Форматирует список сообщений в текст."""
        result_parts = []
        for msg in messages:
            if hasattr(msg, "parts"):
                # Message объект
                for part in msg.parts:
                    if hasattr(part, "root") and hasattr(part.root, "text"):
                        result_parts.append(part.root.text)
            elif isinstance(msg, dict):
                # Сериализованный Message (после to_dict)
                if "parts" in msg:
                    for part in msg["parts"]:
                        if isinstance(part, dict):
                            if "text" in part:
                                result_parts.append(part["text"])
                elif "content" in msg:
                    result_parts.append(str(msg["content"]))
                elif "text" in msg:
                    result_parts.append(str(msg["text"]))
        return "\n".join(result_parts)


class ExternalAPINode(BaseNode):
    """Вызов внешнего HTTP API."""

    def __init__(
        self,
        node_id: str,
        api_config: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(node_id, config)
        self.api_config = api_config or (config if config else {})

    @classmethod
    def from_config(cls, node_id: str, config: Dict[str, Any]) -> "ExternalAPINode":
        """Создает ExternalAPINode из конфига."""
        return cls(node_id=node_id, api_config=config, config=config)

    async def run(self, state: ExecutionState) -> ExecutionState:
        """Вызывает внешний API."""
        mock_data = self._check_mock(state)
        if mock_data is not None:
            logger.info(f"[node:{self.node_id}] using mock data")
            for key, value in mock_data.items():
                setattr(state, key, value)
            return state

        parameters = []
        for p in self.api_config.get("parameters", []):
            if isinstance(p, dict):
                parameters.append(ParameterSchema(**p))

        api_cfg = ExternalAPIConfig(
            api_id=self.node_id,
            name=self.api_config.get("name", self.node_id),
            description=self.api_config.get("description"),
            url=self.api_config.get("url"),
            method=self.api_config.get("method", "POST"),
            headers=self.api_config.get("headers", {}),
            auth_headers=self.api_config.get("auth_headers", {}),
            parameters=parameters,
            timeout=self.api_config.get("timeout", 30.0),
            state_mapping=self.api_config.get("state_mapping", {}),
        )

        variables = state.variables

        args = {}
        for param in api_cfg.parameters:
            if param.source:
                args[param.name] = MappingResolver.resolve_value(param.source, state)
            elif hasattr(state, param.name):
                args[param.name] = getattr(state, param.name)
            elif param.default is not None:
                args[param.name] = param.default

        client = ExternalAPIClient(timeout=api_cfg.timeout)
        result = await client.call(api_cfg, args, variables)

        if result.get("status") == "waiting_input" and result.get("interrupt"):
            interrupt_data = result["interrupt"]
            state.interrupt = InterruptData(question=interrupt_data.get("question", ""))
            return state

        if result.get("status") == "error":
            raise ValueError(f"External API error: {result.get('error')}")

        for response_field, state_field in api_cfg.state_mapping.items():
            data = result.get("data", {})
            if isinstance(data, dict) and response_field in data:
                setattr(state, state_field, data[response_field])

        setattr(state, "api_response", result.get("data"))
        setattr(state, "api_status", result.get("status"))

        return state


async def create_node(node_id: str, node_config: Dict[str, Any]) -> BaseNode:
    """
    Создаёт ноду через NodeRegistry.
    
    Zero-Guess: неизвестный тип = исключение.
    """
    node_type_value = node_config.get("type")
    if node_type_value is None:
        raise ValueError(f"Node '{node_id}': type is required")
    
    try:
        node_type = NodeType(node_type_value) if isinstance(node_type_value, str) else node_type_value
    except ValueError:
        raise ValueError(f"Unknown node type: {node_type_value}")
    
    container = get_container()
    try:
        node_class = container.node_registry.get(node_type)
    except ResourceNotFoundError:
        raise ValueError(f"Unknown node type: {node_type_value}")
    
    return node_class.from_config(node_id, node_config)
