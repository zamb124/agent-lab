"""
Ноды для Agent.

Нода = функция ExecutionState -> ExecutionState.
Маршрутизация через edges в Agent, не в нодах.

Типы нод:
- ReactNode - LLM нода с ReAct циклом
- CodeNode - выполнение кода (Python, JavaScript, Go)
- AgentNode - вложенный agent
- RemoteAgentNode - внешний агент по A2A протоколу
- ExternalAPINode - вызов внешнего HTTP API
- MCPNode - вызов MCP tool
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from a2a.types import Message, Part, Role, TextPart

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
from core.state import ExecutionState, InterruptData
from core.logging import get_logger
from core.errors import ResourceNotFoundError

logger = get_logger(__name__)


class NodeRunMethod:
    """Callable wrapper для node.run() с поддержкой .kiq()"""

    def __init__(self, node: "BaseNode"):
        self._node = node

    async def __call__(self, state: ExecutionState) -> ExecutionState:
        """Прямой вызов в текущем процессе."""
        return await self._node._run_internal(state)

    async def kiq(self, state: ExecutionState) -> ExecutionState:
        """Через воркер если use_worker=True, иначе локально."""
        from apps.agents.src.container import get_container

        container = get_container()
        
        # Внутри воркера выполняем локально
        if not container.use_worker:
            return await self._node._run_internal(state)

        # Отправляем в воркер
        from apps.agents.src.tasks.node_tasks import execute_node

        state_dict = state.model_dump(exclude_none=False)
        task = await execute_node.kiq(
            self._node.node_id,
            self._node.config,
            state_dict
        )
        result = await task.wait_result()
        if result.is_err:
            raise result.error
        return ExecutionState.model_validate(result.return_value)


class NodeRunDescriptor:
    """Descriptor для node.run"""

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return NodeRunMethod(obj)


class BaseNode(ABC):
    """
    Базовый класс для нод. Node = функция ExecutionState -> ExecutionState.
    
    Template Method паттерн:
    - run(state) или run.kiq(state) - единая точка входа для всех нод
    - _resolve_inputs() - единообразный резолвинг input_mapping
    - _get_filtered_messages() - фильтрация messages
    - _run_impl() - конкретная логика каждой ноды
    
    Конфигурация:
    - input_mapping: Dict - маппинг входных данных из state
    - output_mapping: Dict[str, str] - маппинг полей результата -> state fields
    - save_to_messages: bool - добавлять результат в messages
    - message_field: str - какое поле писать в messages (по умолчанию diff стейта)
    - messages_filter: "all" / "own" / List[str] - фильтрация входящих messages
    
    Контракт _run_impl() для ВСЕХ нод:
    - Возвращает Any (dict, str, None, etc)
    - dict: поля записываются в state через output_mapping
    - не dict и не None: записывается в state.result
    - None: ничего не записывается
    """

    name: str = "node"
    description: Optional[str] = None

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        self.node_id = node_id
        self.config = config or {}
        self.input_mapping = self.config.get("input_mapping")
        self.output_mapping: Optional[Dict[str, str]] = self.config.get("output_mapping")
        self.save_to_messages = self.config.get("save_to_messages", False)
        self.message_field = self.config.get("message_field")
        self.messages_filter: Union[str, List[str]] = self.config.get("messages_filter", "all")

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

    def _resolve_inputs(self, state: ExecutionState) -> Dict[str, Any]:
        """
        Единообразный резолвинг input_mapping для всех типов нод.
        
        Returns:
            Dict с резолвнутыми значениями из input_mapping
        """
        if not self.input_mapping:
            return {}
        return MappingResolver.build_mapped_state(self.input_mapping, state)

    def _get_filtered_messages(self, state: ExecutionState) -> List[Message]:
        """
        Возвращает отфильтрованные messages.
        
        Фильтры:
        - "all" - все сообщения
        - "own" - только свои (node_id совпадает) + user messages
        - List[str] - от указанных node_id + user messages
        """
        all_messages = state.messages or []
        
        if self.messages_filter == "all":
            return list(all_messages)
        
        if self.messages_filter == "own":
            return [m for m in all_messages 
                    if self._get_message_node_id(m) == self.node_id 
                    or self._is_user_message(m)]
        
        if isinstance(self.messages_filter, list):
            allowed = set(self.messages_filter)
            return [m for m in all_messages 
                    if self._get_message_node_id(m) in allowed
                    or self._is_user_message(m)]
        
        return list(all_messages)

    def _append_to_messages(self, state: ExecutionState, result: Any) -> None:
        """Добавляет результат в messages с маркировкой node_id."""
        text = str(result) if not isinstance(result, str) else result
        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=text))],
            metadata={"node_id": self.node_id},
            task_id=state.task_id,
        )
        state.messages.append(message)

    @staticmethod
    def _get_message_node_id(msg: Message) -> Optional[str]:
        """Извлекает node_id из metadata сообщения."""
        metadata = getattr(msg, "metadata", None) or {}
        return metadata.get("node_id")

    @staticmethod
    def _is_user_message(msg: Message) -> bool:
        """Проверяет является ли сообщение от пользователя."""
        return getattr(msg, "role", None) == Role.user

    async def _resolve_resources(self, state: ExecutionState) -> Dict[str, Any]:
        """
        Резолвит ресурсы для ноды.
        
        Иерархия (node > skill > agent):
        - agent_config.resources - ресурсы агента
        - agent_config.skills[skill_id].resources - ресурсы skill
        - node config resources - ресурсы ноды
        
        Returns:
            Dict[resource_id, wrapper] для использования в namespace
        """
        container = get_container()
        
        # Ресурсы из agent_config (inline в state)
        agent_resources = state.agent_config.get("resources", {})
        
        # Ресурсы skill (если есть)
        skill_resources = None
        skill_id = state.skill_id
        if skill_id and skill_id != "default":
            skills = state.agent_config.get("skills", {})
            skill_config = skills.get(skill_id, {})
            skill_resources = skill_config.get("resources")
        
        # Ресурсы ноды из конфига
        node_resources = self.config.get("resources", {})
        
        if not agent_resources and not skill_resources and not node_resources:
            return {}
        
        return await container.resource_resolver.resolve_for_node(
            agent_resources=agent_resources,
            skill_resources=skill_resources,
            node_resources=node_resources,
            variables=state.variables,
        )

    # Descriptor для унифицированного вызова: node.run(state) или node.run.kiq(state)
    run = NodeRunDescriptor()

    async def _run_internal(self, state: ExecutionState) -> ExecutionState:
        """
        Внутренняя реализация выполнения ноды.
        
        1. Проверка mock
        2. Сохранение snapshot для diff (если save_to_messages без message_field)
        3. Резолвинг input_mapping -> inputs
        4. Выполнение _run_impl(state, inputs)
        5. Обработка результата:
           - ExecutionState: мержим в текущий state
           - dict: записываем поля в state через output_mapping
        6. Добавление в messages если save_to_messages=True
        """
        mock_data = self._check_mock(state)
        if mock_data is not None:
            logger.info(f"[node:{self.node_id}] using mock data")
            for key, value in mock_data.items():
                setattr(state, key, value)
            return state
        
        state_before = None
        if self.save_to_messages and not self.message_field:
            state_before = state.model_dump(exclude_none=False)
        
        inputs = self._resolve_inputs(state)
        
        result = await self._run_impl(state, inputs)
        
        if result is not None:
            if isinstance(result, ExecutionState):
                self._copy_state_back(result, state)
            else:
                self._apply_output_mapping(state, result)
        
        if self.save_to_messages:
            message_content = self._get_message_content(state, state_before, result)
            if message_content:
                self._append_to_messages(state, message_content)
        
        return state
    
    def _apply_output_mapping(self, state: ExecutionState, result: Any) -> None:
        """
        Записывает результат в state через output_mapping.
        
        Если result - dict:
          - С output_mapping: result[key] -> state[mapped_field]
          - Без output_mapping: result[key] -> state[key] (напрямую)
        Если result - не dict:
          - Записываем в state.result
        """
        if isinstance(result, dict):
            if self.output_mapping:
                for result_key, state_field in self.output_mapping.items():
                    if result_key in result:
                        setattr(state, state_field, result[result_key])
            else:
                for key, value in result.items():
                    setattr(state, key, value)
        else:
            setattr(state, "result", result)
    
    def _get_message_content(
        self, state: ExecutionState, state_before: Optional[Dict], result: Any
    ) -> Optional[str]:
        """
        Определяет что записать в messages.
        
        Приоритет поиска message_field:
        1. result[message_field] если result - dict
        2. state.message_field
        """
        if self.message_field:
            value = None
            if isinstance(result, dict) and self.message_field in result:
                value = result[self.message_field]
            else:
                value = getattr(state, self.message_field, None)
            return str(value) if value is not None else None
        elif state_before:
            return self._compute_state_diff(state_before, state)
        else:
            return str(result) if result is not None else None
    
    def _compute_state_diff(
        self, state_before: Dict[str, Any], state_after: ExecutionState
    ) -> Optional[str]:
        """Вычисляет diff между состояниями для записи в messages."""
        state_after_dict = state_after.model_dump(exclude_none=False)
        
        skip_fields = {"messages", "prompt_history", "node_history", "nested_states"}
        
        diff_parts = []
        for key, new_value in state_after_dict.items():
            if key in skip_fields:
                continue
            old_value = state_before.get(key)
            if old_value != new_value and new_value is not None:
                diff_parts.append(f"{key}: {new_value}")
        
        if not diff_parts:
            return None
        return "\n".join(diff_parts)

    @abstractmethod
    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """
        Конкретная логика ноды.
        
        Args:
            state: ExecutionState для чтения/записи
            inputs: Резолвнутые данные из input_mapping
            
        Returns:
            Результат (dict - поля записываются в state через output_mapping)
        """
        pass

    def _copy_state_back(self, source: ExecutionState, target: ExecutionState) -> None:
        """Копирует все изменения из source обратно в target."""
        for field_name in ExecutionState.model_fields:
            if hasattr(source, field_name):
                setattr(target, field_name, getattr(source, field_name))
        
        if hasattr(source, '__pydantic_extra__') and source.__pydantic_extra__:
            if not hasattr(target, '__pydantic_extra__') or target.__pydantic_extra__ is None:
                target.__pydantic_extra__ = {}
            target.__pydantic_extra__.update(source.__pydantic_extra__)

    def _prepare_state(self, state: ExecutionState, inputs: Dict[str, Any]) -> ExecutionState:
        """
        Создает state для вложенного выполнения.
        Применяет inputs и фильтрует messages.
        Сбрасывает current_nodes чтобы nested agent начал со своего entry.
        """
        new_state = ExecutionState.model_validate(state.model_dump(exclude_none=False))
        
        for key, value in inputs.items():
            setattr(new_state, key, value)
        
        new_state.messages = self._get_filtered_messages(state)
        
        # Сбрасываем current_nodes - nested agent начнет со своего entry
        new_state.current_nodes = []
        
        return new_state

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
        config: Optional[Dict[str, Any]] = None,
        node_config: Optional[NodeConfig] = None,
    ):
        super().__init__(node_id or self.name, config)
        cfg = self.config
        
        self.prompt_template = self.prompt or cfg.get("prompt", "")
        self.tool_refs = cfg.get("tools", []) or self.tools
        self.llm_config_dict = cfg.get("llm", {})
        
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

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """
        Выполняет ReAct цикл.
        
        _copy_state_back мержит все изменения из agent_state обратно в state.
        При structured_output возвращает dict с полями из JSON ответа.
        """
        agent_state = self._prepare_state(state, inputs)

        if self.tool_refs and self._loaded_tools is None:
            self._loaded_tools = await self._load_tools(agent_state)

        logger.info(f"[node:{self.node_id}] Запуск ReactNode")

        content = agent_state.content or ""
        input_data = {"content": content}

        try:
            runner = await self.get_runner(agent_state)
            async for _ in runner.run(input_data, agent_state):
                pass
        finally:
            self._copy_state_back(agent_state, state)

        # При structured output возвращаем dict для записи в state через output_mapping
        structured_result = getattr(state, "structured_output_result", None)
        if structured_result is not None:
            return structured_result
        
        return {"response": state.response} if state.response else None

    async def get_runner(self, state: Optional[ExecutionState] = None):
        """Возвращает runner для ReactNode."""
        if self._runner is not None:
            return self._runner

        tools = await self.get_tools(state)
        llm = self._get_llm(state)
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

    async def get_tools(self, state: Optional[ExecutionState] = None) -> List[Any]:
        """Возвращает список tools."""
        if self._loaded_tools is not None:
            return self._loaded_tools
        
        # Загружаем tools из tool_refs если они есть
        if self.tool_refs:
            self._loaded_tools = await self._load_tools(state)
            return self._loaded_tools
        
        # Если нет tool_refs, возвращаем атрибут класса tools (для кастомных нод)
        # Атрибут класса tools должен содержать уже готовые объекты, не конфиги
        return self.tools

    async def set_tools(self, tools: List[Any]) -> None:
        """Устанавливает tools."""
        self._loaded_tools = tools

    def _get_llm(self, state: Optional[ExecutionState] = None):
        """Возвращает LLM клиент."""
        model = None
        temp = None
        provider = None
        api_key = None
        base_url = None

        if self._node_config and self._node_config.llm_override:
            override = self._node_config.llm_override
            model = override.model
            temp = override.temperature
            provider = override.provider
            api_key = override.api_key
            base_url = override.base_url
        elif self.llm_config_dict:
            model = self.llm_config_dict.get("model")
            temp = self.llm_config_dict.get("temperature")
            provider = self.llm_config_dict.get("provider")
            api_key = self.llm_config_dict.get("api_key")
            base_url = self.llm_config_dict.get("base_url")

        logger.info(f"[_get_llm] node_id={self.node_id}, model={model}, temp={temp}, provider={provider}")
        return get_llm(
            model_name=model,
            temperature=temp,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            state=state,
        )

    def _create_default_config(self) -> NodeConfig:
        """Создает конфигурацию по умолчанию."""
        llm_override = None
        if self.llm_config_dict:
            llm_override = NodeLLMOverride(
                model=self.llm_config_dict.get("model"),
                temperature=self.llm_config_dict.get("temperature"),
                provider=self.llm_config_dict.get("provider"),
                api_key=self.llm_config_dict.get("api_key"),
                base_url=self.llm_config_dict.get("base_url"),
            )

        react_config = None
        react_dict = self.config.get("react") if self.config else None
        if react_dict:
            react_config = ReactConfig(**react_dict)
        
        # Structured output из config
        structured_output = self.config.get("structured_output", False) if self.config else False
        output_schema = self.config.get("output_schema") if self.config else None
            
        return NodeConfig(
            node_id=self.node_id,
            type=NodeType.REACT_NODE,
            name=self.node_id,
            description=self.description or "",
            prompt=self.prompt_template or self.prompt or "",
            llm_override=llm_override,
            react=react_config,
            structured_output=structured_output,
            output_schema=output_schema,
        )

    async def _load_tools(self, state: Optional[ExecutionState] = None) -> List[Any]:
        """
        Создаёт tools из inline конфигов.
        
        Иерархия resources для tools как у CodeNode: agent → node → tool (правее сильнее).
        """
        container = get_container()
        
        agent_resources = {}
        skill_resources = {}
        if state is not None:
            agent_resources = (state.agent_config or {}).get("resources") or {}
            skill_id = getattr(state, "skill_id", None)
            if skill_id and skill_id != "default":
                skills = (state.agent_config or {}).get("skills", {}) or {}
                skill_cfg = skills.get(skill_id, {}) or {}
                skill_resources = skill_cfg.get("resources") or {}
        node_resources_cfg = self.config.get("resources", {}) or {}
        merged_node_level = {**agent_resources, **skill_resources, **node_resources_cfg}
        
        if merged_node_level:
            enriched_refs = []
            for ref in self.tool_refs:
                if isinstance(ref, dict):
                    tool_resources = ref.get("resources", {}) or {}
                    merged_resources = {**merged_node_level, **tool_resources}
                    enriched_ref = {**ref, "resources": merged_resources}
                    enriched_refs.append(enriched_ref)
                else:
                    enriched_refs.append(ref)
            return await container.tool_registry.create_tools(enriched_refs)
        
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

    async def run(self, args: Dict[str, Any], state: ExecutionState) -> str:
        """Выполняет ноду как tool."""
        request = args.get("request", "")
        node_name = getattr(self.node, "react_node_name", self.node.node_id)
        logger.info(f"NodeAsTool: вызов {node_name} с запросом: {request[:100]}")
        
        state.content = request
        await self.node.run(state)
        return state.response or "Нет ответа от ноды"

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


class CodeNode(BaseNode):
    """
    Универсальная нода для выполнения кода.
    
    Поддерживает разные языки (python, javascript, go).
    Унифицированный вызов через runner.execute_tool(code, args, state).
    
    args_schema опционален - если задан, args заполняются из inputs,
    если нет - args будет пустым dict.
    
    tool_id - загрузка готового tool из реестра вместо inline кода.
    """

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        cfg = self.config
        
        self.language = cfg.get("language", "python")
        self.code = cfg.get("code")
        self.tool_id = cfg.get("tool_id")
        self.args_schema = cfg.get("args_schema")
        
        self._runner = None
        self._registry_tool = None
        
        # Для Python можно загрузить из function path
        if self.language == "python" and self.code is None and cfg.get("function"):
            self._load_from_function_path(cfg["function"])

    def _load_from_function_path(self, function_path: str):
        """Загружает код из module.function path."""
        try:
            module_path, func_name = function_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            self.code = inspect.getsource(func)
        except Exception as e:
            raise ValueError(f"Node '{self.node_id}': failed to load from {function_path}: {e}")

    def _get_runner(self, resources: Optional[Dict[str, Any]] = None):
        """Возвращает runner для текущего языка с ресурсами."""
        container = get_container()
        return container.get_code_runner(self.language, resources=resources)

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """
        Выполняет код через runner.execute_tool().
        
        Унифицированный путь: всегда execute_tool(code, args, state).
        args формируется из inputs (может быть пустым).
        """
        # Загрузка tool из реестра
        if self.tool_id:
            return await self._run_registry_tool(state, inputs)
        
        if not self.code:
            raise ValueError(f"Node '{self.node_id}': code or tool_id required")
        
        args = self._build_args(inputs)
        logger.info(f"[node:{self.node_id}] execute_tool с args: {list(args.keys())}")
        
        # Резолвим ресурсы для ноды
        resources = await self._resolve_resources(state)
        
        runner = self._get_runner(resources=resources)
        return await runner.execute_tool(self.code, args, state)

    async def _run_registry_tool(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """Выполняет tool загруженный из реестра."""
        if self._registry_tool is None:
            container = get_container()
            self._registry_tool = await container.tool_registry.create_tool({"tool_id": self.tool_id})
            if self._registry_tool is None:
                raise ValueError(f"Tool '{self.tool_id}' not found")
        
        args = self._build_args(inputs)
        logger.info(f"[node:{self.node_id}] registry tool '{self._registry_tool.name}' с args: {list(args.keys())}")
        return await self._registry_tool.run(args, state)

    def _build_args(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Формирует args из inputs с учетом defaults из args_schema."""
        args = {}
        
        if self.args_schema:
            for name, schema in self.args_schema.items():
                if "default" in schema:
                    args[name] = schema["default"]
        
        args.update(inputs)
        return args


class AgentNode(BaseNode):
    """Вложенный Agent с поддержкой skill."""

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        cfg = self.config
        
        self.agent_id = cfg.get("agent_id")
        self.skill_id = cfg.get("skill_id", "default")
        self._agent = None

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """
        Запускает вложенный Agent.
        
        _copy_state_back мержит изменения из вложенного агента обратно в state.
        """
        if not self.agent_id:
            raise ValueError(f"Node '{self.node_id}': agent_id required")

        nested_state = self._prepare_state(state, inputs)

        if self._agent is None:
            container = get_container()
            self._agent = await container.agent_factory.get_flow(self.agent_id, self.skill_id)

        result = await self._agent.run(nested_state)
        self._copy_state_back(result, state)
        
        return state.response


class RemoteAgentNode(BaseNode):
    """Внешний агент по A2A протоколу."""

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        cfg = self.config
        
        self.url = cfg.get("url")
        self.remote_agent_id = cfg.get("agent_id")
        self.skill_id = cfg.get("skill_id", "default")
        self.auth_headers_config = cfg.get("auth_headers", {})

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """Вызывает внешнего агента."""
        if not self.url and not self.remote_agent_id:
            raise ValueError("RemoteAgentNode requires 'url' or 'agent_id'")

        container = get_container()
        variables = state.variables

        url, auth_headers = await self._resolve_connection(container, variables)

        content = inputs.get("content", state.content or "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)

        result = await container.a2a_client.send_task(
            base_url=url,
            content=content,
            session_id=state.session_id,
            skill_id=self.skill_id,
            auth_headers=auth_headers,
        )

        state.response = result.get("response", "")
        setattr(state, "remote_status", result.get("status", "completed"))
        return result.get("response", "")

    async def _resolve_connection(
        self, container, variables: Dict[str, Any]
    ) -> tuple[str, Dict[str, str]]:
        """Резолвит URL и auth headers."""
        if self.remote_agent_id:
            agent = await container.agent_discovery.get_agent(self.remote_agent_id)
            if agent is None:
                raise ValueError(f"External agent '{self.remote_agent_id}' not found in registry")
            return agent.url, agent.auth_headers
        
        url = self._resolve_value(self.url, variables)
        auth_headers = self._resolve_auth_headers(self.auth_headers_config, variables)
        return url, auth_headers

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


class ExternalAPINode(BaseNode):
    """Вызов внешнего HTTP API."""

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        self.api_config = self.config

    def _build_api_config(self) -> ExternalAPIConfig:
        """Строит конфиг API."""
        parameters = []
        for p in self.api_config.get("parameters", []):
            if isinstance(p, dict):
                parameters.append(ParameterSchema(**p))

        return ExternalAPIConfig(
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

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """Вызывает внешний API с inputs как аргументами."""
        api_cfg = self._build_api_config()
        variables = state.variables

        # Если input_mapping не задан, автоматически берем параметры из state
        if not inputs:
            for param in api_cfg.parameters:
                value = state.get(param.name)
                if value is not None:
                    inputs[param.name] = value

        client = ExternalAPIClient(timeout=api_cfg.timeout)
        result = await client.call(api_cfg, inputs, variables)

        if result.get("status") == "waiting_input" and result.get("interrupt"):
            interrupt_data = result["interrupt"]
            state.interrupt = InterruptData(question=interrupt_data.get("question", ""))
            return None

        if result.get("status") == "error":
            raise ValueError(f"External API error: {result.get('error')}")

        for response_field, state_field in api_cfg.state_mapping.items():
            data = result.get("data", {})
            if isinstance(data, dict) and response_field in data:
                setattr(state, state_field, data[response_field])

        setattr(state, "api_response", result.get("data"))
        setattr(state, "api_status", result.get("status"))

        return result.get("data")


class MCPNode(BaseNode):
    """
    Вызов MCP tool как нода графа.
    
    Подключается к MCP серверу и вызывает указанный tool.
    """

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        cfg = self.config
        
        self.server_id = cfg.get("server_id")
        self.tool_name = cfg.get("tool_name")
        self.extra_headers = cfg.get("headers", {})
        self.state_mapping = cfg.get("state_mapping", {})

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """Вызывает MCP tool."""
        if not self.server_id:
            raise ValueError(f"MCPNode '{self.node_id}': server_id is required")
        if not self.tool_name:
            raise ValueError(f"MCPNode '{self.node_id}': tool_name is required")
        
        container = get_container()
        
        server = await container.mcp_server_repository.get(self.server_id)
        if not server:
            raise ValueError(f"MCP server not found: {self.server_id}")
        
        if self.extra_headers:
            merged_headers = {**server.headers, **self.extra_headers}
            server.headers = merged_headers
        
        variables = state.variables
        
        from apps.agents.src.clients.mcp_client import MCPHttpClient
        
        client = MCPHttpClient(server, variables)
        result = await client.call_tool(self.tool_name, inputs)
        
        if result.is_error:
            raise ValueError(f"MCP tool error: {result.get_text()}")
        
        text_result = result.get_text()
        
        for field, state_field in self.state_mapping.items():
            setattr(state, state_field, text_result)
        
        setattr(state, "mcp_result", text_result)
        
        return text_result


class ChannelNode(BaseNode):
    """
    Универсальная нода отправки сообщений в каналы.
    
    Поддерживаемые каналы: telegram, email, webhook, whatsapp, sms.
    
    Конфигурация:
    {
        "type": "channel",
        "channel": "telegram",
        "action": "send_message",
        "channel_config": {
            "bot_token": "@var:my_bot_token",
            "parse_mode": "HTML"
        },
        "input_mapping": {
            "recipient": "@state:variables.chat_id",
            "text": "@state:response"
        }
    }
    
    Поддерживаемые actions:
    - send_message: текстовое сообщение
    - send_photo: фото с подписью
    - send_document: документ/файл
    - send_payload: произвольный JSON (для webhook)
    - send_notification: A2A нотификация (для webhook)
    """

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        cfg = self.config
        
        from apps.agents.src.models.enums import ChannelType
        
        channel_value = cfg.get("channel", "telegram")
        self.channel = ChannelType(channel_value) if isinstance(channel_value, str) else channel_value
        self.action = cfg.get("action", "send_message")
        self.channel_config = cfg.get("channel_config", {})

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """Отправляет сообщение через channel handler."""
        from apps.agents.src.variables import VariableResolver
        
        container = get_container()
        handler = container.channel_registry.get(self.channel)
        
        # Собираем все переменные (агента, компании, системные)
        all_variables = VariableResolver.resolve_all(local_vars=state.variables)
        
        # Merge channel_config с inputs
        config = {**self.channel_config}
        
        # Резолвим @var: в channel_config используя все переменные
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("@var:"):
                var_key = value[5:]
                resolved = all_variables.get(var_key)
                if resolved is None:
                    raise ValueError(f"Variable not found: {var_key}")
                config[key] = resolved
        
        result = await handler.execute_action(
            action=self.action,
            params=inputs,
            config=config,
            variables=all_variables,
        )
        
        setattr(state, "channel_result", result)
        
        logger.info(
            f"[node:{self.node_id}] Channel {self.channel.value} "
            f"action {self.action} completed"
        )
        
        return result


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
