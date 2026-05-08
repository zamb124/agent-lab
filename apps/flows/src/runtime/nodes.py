"""
Ноды для Flow runtime.

Нода = функция ExecutionState -> ExecutionState.
Маршрутизация через edges во Flow, не в нодах.

Типы нод:
- LlmNode - LLM нода с ReAct циклом
- CodeNode - выполнение кода (Python, JavaScript, Go)
- FlowNode - вложенный flow
- RemoteFlowNode - внешний flow по A2A протоколу
- ExternalAPINode - вызов внешнего HTTP API
- MCPNode - вызов MCP tool
- ResourceNode - нода-ресурс на графе (identity / pass-through)
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.runtime.exceptions import BreakpointInterrupt, FlowInterrupt
from apps.flows.src.runtime.exception_policy import node_exception_policy, should_absorb_exception
from apps.flows.src.runtime.llm_resource_override import (
    infer_unique_llm_resource_key_from_merged_maps,
    resolve_llm_override_with_resource_key,
)
from apps.flows.src.runtime.runners import LlmNodeRunner
from apps.flows.src.clients.external_api_client import ExternalAPIClient
from core.clients.llm import get_llm
from apps.flows.src.container import get_container
from apps.flows.src.mapping import MappingResolver
from apps.flows.src.mock import get_mock_for_node
from apps.flows.src.models import NodeLLMOverride, NodeConfig, ReactConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.operator_schemas import OperatorTaskStatus
from apps.flows.src.models.external_api import ExternalAPIConfig, ParameterSchema
from core.context import get_context as get_request_context
from core.state import (
    ExecutionExceptionRecord,
    ExecutionState,
    parse_interrupt_body_from_external_dict,
)
from core.state.mutation_policy import (
    forbid_frozen_update_key,
    should_skip_field_on_user_returned_state_copy,
)
from core.state.interrupt import HandoffMode, OperatorTaskInterrupt
from apps.flows.src.state.interrupt_manager import InterruptManager
from core.logging import get_logger
from core.errors import NodeWallClockTimeoutError, ResourceNotFoundError
from core.tracing.operation_span import traced_operation

if TYPE_CHECKING:
    from apps.flows.src.tools.node_wrapper import NodeAsToolWrapper

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
        from apps.flows.src.container import get_container

        container = get_container()
        
        # Внутри воркера выполняем локально
        if not container.use_worker:
            return await self._node._run_internal(state)

        # Отправляем в воркер
        from apps.flows.src.tasks.node_tasks import execute_node

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
    - messages_filter: "all" / "own" / List[str] — срез по metadata.node_id
    
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
        - "all" — все сообщения
        - "own" — только сообщения с metadata.node_id == node_id этой ноды
        - List[str] — только сообщения, у которых metadata.node_id входит в список
        """
        all_messages = state.messages or []

        if self.messages_filter == "all":
            return list(all_messages)

        if self.messages_filter == "own":
            return [
                m for m in all_messages
                if self._get_message_node_id(m) == self.node_id
            ]

        if isinstance(self.messages_filter, list):
            allowed = set(self.messages_filter)
            return [
                m for m in all_messages
                if self._get_message_node_id(m) in allowed
            ]

        raise ValueError(
            f"messages_filter: ожидается 'all', 'own' или list[str], получено {self.messages_filter!r}"
        )

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

    async def _resolve_resources(self, state: ExecutionState) -> Dict[str, Any]:
        """
        Резолвит ресурсы для ноды.
        
        Иерархия (node > skill > flow): flow/skill из БД по session_flow_id и flow_config_version.
        
        Returns:
            Dict[resource_id, wrapper] для использования в namespace
        """
        container = get_container()
        
        flow_resources, skill_resources = await container.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        
        # Ресурсы ноды из конфига
        node_resources = self.config.get("resources", {})
        
        if not flow_resources and not skill_resources and not node_resources:
            return {}
        
        return await container.resource_resolver.resolve_for_node(
            flow_resources=flow_resources,
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

        node_timeout = self.config.get("node_timeout_seconds")
        nto: Optional[int] = None
        try:
            if node_timeout is not None:
                nto = int(node_timeout)
                result = await asyncio.wait_for(
                    self._run_impl(state, inputs),
                    timeout=float(nto),
                )
            else:
                result = await self._run_impl(state, inputs)
        except asyncio.TimeoutError as e:
            if nto is None:
                raise
            raise NodeWallClockTimeoutError(self.node_id, nto) from e
        except (FlowInterrupt, BreakpointInterrupt):
            raise
        except asyncio.CancelledError:
            raise
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            enabled, allow_types = node_exception_policy(self.config)
            if not should_absorb_exception(e, enabled=enabled, allow_types=allow_types):
                raise
            state.execution_exceptions.append(
                ExecutionExceptionRecord(
                    node_id=self.node_id,
                    source="node_run",
                    exception_type=type(e).__name__,
                    message=str(e),
                )
            )
            result = {
                "error": True,
                "error_type": type(e).__name__,
                "message": str(e),
            }

        if result is not None:
            if isinstance(result, ExecutionState):
                self._copy_state_back(result, state, full_trust=False)
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
                        forbid_frozen_update_key(state_field, reason="output_mapping")
                        setattr(state, state_field, result[result_key])
            else:
                for key, value in result.items():
                    forbid_frozen_update_key(key, reason="output_mapping")
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

    def _copy_state_back(
        self,
        source: ExecutionState,
        target: ExecutionState,
        *,
        full_trust: bool = True,
    ) -> None:
        """Копирует изменения из source в target. full_trust=False — не переносить системные поля."""
        for field_name in ExecutionState.model_fields:
            if not full_trust and should_skip_field_on_user_returned_state_copy(field_name):
                continue
            if hasattr(source, field_name):
                setattr(target, field_name, getattr(source, field_name))

        if hasattr(source, "__pydantic_extra__") and source.__pydantic_extra__:
            if not hasattr(target, "__pydantic_extra__") or target.__pydantic_extra__ is None:
                target.__pydantic_extra__ = {}
            if full_trust:
                target.__pydantic_extra__.update(source.__pydantic_extra__)
            else:
                for ek, ev in source.__pydantic_extra__.items():
                    if should_skip_field_on_user_returned_state_copy(ek):
                        continue
                    target.__pydantic_extra__[ek] = ev

    def _prepare_state(self, state: ExecutionState, inputs: Dict[str, Any]) -> ExecutionState:
        """
        Создает state для вложенного выполнения.
        Применяет inputs и фильтрует messages.
        Сбрасывает current_nodes чтобы вложенный flow начал со своего entry.
        """
        new_state = ExecutionState.model_validate(state.model_dump(exclude_none=False))
        
        for key, value in inputs.items():
            setattr(new_state, key, value)
        
        new_state.messages = self._get_filtered_messages(state)
        
        # Сбрасываем current_nodes — вложенный flow начнёт со своего entry
        new_state.current_nodes = []
        
        return new_state

    def as_tool(
        self, name: Optional[str] = None, description: Optional[str] = None
    ) -> "NodeAsToolWrapper":
        """
        Превращает ноду в tool (тот же NodeAsToolWrapper, что и в ToolRegistry).
        """
        from apps.flows.src.tools.node_wrapper import NodeAsToolWrapper

        return NodeAsToolWrapper.from_base_node(
            self,
            tool_name=name or f"{self.node_id}_tool",
            tool_description=description
            or self.description
            or f"Вызов ноды {self.node_id}",
        )


class LlmNode(BaseNode):
    """
    LLM нода (ReAct цикл + tools).

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
    name: str = "llm_node"
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
        raw_override = cfg.get("llm_override")
        raw_llm = cfg.get("llm")
        if isinstance(raw_override, dict):
            if raw_override:
                self.llm_config_dict = dict(raw_override)
            elif isinstance(raw_llm, dict):
                self.llm_config_dict = dict(raw_llm)
            else:
                self.llm_config_dict = {}
        elif isinstance(raw_llm, dict):
            self.llm_config_dict = dict(raw_llm)
        else:
            self.llm_config_dict = {}
        
        self._node_config = node_config
        self._runner = None
        self._loaded_tools: Optional[List[Any]] = None
        if node_config is not None:
            self.messages_filter = node_config.messages_filter

    def _prepare_llm_runner_state(
        self, state: ExecutionState, inputs: Dict[str, Any]
    ) -> ExecutionState:
        """
        Копия state для раннера LLM: общий список messages с родителем (полный лог), без подмены фильтром.
        """
        new_state = ExecutionState.model_validate(state.model_dump(exclude_none=False))
        for key, value in inputs.items():
            setattr(new_state, key, value)
        new_state.messages = state.messages
        new_state.current_nodes = list(state.current_nodes)
        return new_state

    @property
    def llm_node_id(self) -> str:
        """ID ноды"""
        if self._node_config:
            return self._node_config.node_id
        return self.node_id

    @property
    def llm_config(self) -> Dict[str, Any]:
        """LLM конфигурация."""
        return self.llm_config_dict

    @property
    def llm_node_name(self) -> str:
        """Название ноды"""
        if self._node_config:
            return self._node_config.name
        return self.name

    @property
    def llm_node_description(self) -> Optional[str]:
        """Описание ноды"""
        if self._node_config and self._node_config.description:
            return self._node_config.description
        return self.description

    @property
    def llm_node_prompt(self) -> Optional[str]:
        """Промпт ноды"""
        if self._node_config and self._node_config.prompt:
            return self._node_config.prompt
        return self.prompt_template or self.prompt

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """
        Выполняет ReAct цикл.
        
        _copy_state_back мержит все изменения из рабочей копии state обратно в state.
        При structured_output возвращает dict с полями из JSON ответа.
        """
        runner_state = self._prepare_llm_runner_state(state, inputs)

        # structured_output_result используется как одноразовый канал передачи
        # JSON-ответа structured ноды в output_mapping. Его нельзя переносить
        # между нодами — иначе следующая нода "наследует" результат и будет
        # выглядеть как будто вернула structured output, даже если это не так.
        if getattr(runner_state, "structured_output_result", None) is not None:
            delattr(runner_state, "structured_output_result")

        if self.tool_refs and self._loaded_tools is None:
            self._loaded_tools = await self._load_tools(runner_state)

        logger.info(f"[node:{self.node_id}] Запуск LlmNode")

        content = runner_state.content or ""
        input_data = {"content": content}

        try:
            runner = await self.get_runner(runner_state)
            async for _ in runner.run(input_data, runner_state):
                pass
        finally:
            self._copy_state_back(runner_state, state)

        # При structured output возвращаем dict для записи в state через output_mapping
        structured_result = getattr(state, "structured_output_result", None)
        if structured_result is not None:
            delattr(state, "structured_output_result")
            state.response = json.dumps(structured_result, ensure_ascii=False)
            return structured_result

        return {"response": state.response} if state.response else None

    async def get_runner(self, state: Optional[ExecutionState] = None):
        """Возвращает runner для LlmNode."""
        if self._runner is not None:
            return self._runner

        tools = await self.get_tools(state)
        llm = self._get_llm(state)
        prompt = self.llm_node_prompt or ""

        base = self._node_config or self._create_default_config()
        config = await self._resolve_effective_node_config(base, state)

        self._runner = LlmNodeRunner(
            node_config=config,
            tools=tools,
            llm=llm,
            prompt=prompt,
            llm_node=self,
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
        folder_id = None

        if self._node_config and self._node_config.llm_override:
            override = self._node_config.llm_override
            model = override.model
            temp = override.temperature
            provider = override.provider
            api_key = override.api_key
            base_url = override.base_url
            folder_id = override.folder_id
        elif self.llm_config_dict:
            model = self.llm_config_dict.get("model")
            temp = self.llm_config_dict.get("temperature")
            provider = self.llm_config_dict.get("provider")
            api_key = self.llm_config_dict.get("api_key")
            base_url = self.llm_config_dict.get("base_url")
            folder_id = self.llm_config_dict.get("folder_id")

        logger.info(f"[_get_llm] node_id={self.node_id}, model={model}, temp={temp}, provider={provider}")
        max_tok = None
        if self._node_config and self._node_config.llm_override:
            max_tok = self._node_config.llm_override.max_tokens

        return get_llm(
            model_name=model,
            temperature=temp,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            folder_id=folder_id,
            max_tokens=max_tok,
            state=state,
        )

    async def _resolve_effective_node_config(
        self, base: NodeConfig, state: Optional[ExecutionState]
    ) -> NodeConfig:
        ov = base.llm_override
        if not ov:
            return base
        explicit = ov.llm_resource_key and str(ov.llm_resource_key).strip()
        if state is None:
            if explicit:
                raise ValueError("ExecutionState обязателен при заданном llm_resource_key")
            return base
        container = get_container()
        flow_resources, skill_resources = await container.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        node_resources_raw = self.config.get("resources", {}) or {}
        repo = container.resource_repository
        if explicit:
            merged_ov = await resolve_llm_override_with_resource_key(
                llm_override=ov,
                flow_resources=flow_resources or {},
                skill_resources=skill_resources,
                node_resources_raw=node_resources_raw,
                repository=repo,
            )
            return base.model_copy(update={"llm_override": merged_ov})
        inferred = await infer_unique_llm_resource_key_from_merged_maps(
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            repository=repo,
        )
        if inferred is None:
            return base
        ov_with_key = ov.model_copy(update={"llm_resource_key": inferred})
        merged_ov = await resolve_llm_override_with_resource_key(
            llm_override=ov_with_key,
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            repository=repo,
        )
        return base.model_copy(update={"llm_override": merged_ov})

    def _create_default_config(self) -> NodeConfig:
        """Создает конфигурацию по умолчанию."""
        llm_override = None
        if self.llm_config_dict:
            allowed = set(NodeLLMOverride.model_fields.keys())
            raw_llm = {k: v for k, v in self.llm_config_dict.items() if k in allowed}
            llm_override = NodeLLMOverride.model_validate(raw_llm)

        react_config = None
        react_dict = self.config.get("react") if self.config else None
        if react_dict:
            react_config = ReactConfig(**react_dict)
        
        # Structured output из config
        structured_output = self.config.get("structured_output", False) if self.config else False
        output_schema = self.config.get("output_schema") if self.config else None
        messages_filter = self.config.get("messages_filter", "all") if self.config else "all"

        exc_response = False
        exc_allow: list = []
        if self.config:
            if "exception_as_response" in self.config:
                exc_response = bool(self.config["exception_as_response"])
            raw_allow = self.config.get("exception_allow_types")
            if raw_allow is not None:
                exc_allow = raw_allow

        return NodeConfig(
            node_id=self.node_id,
            type=NodeType.LLM_NODE,
            name=self.node_id,
            description=self.description or "",
            prompt=self.prompt_template or self.prompt or "",
            llm_override=llm_override,
            react=react_config,
            structured_output=structured_output,
            output_schema=output_schema,
            messages_filter=messages_filter,
            exception_as_response=exc_response,
            exception_allow_types=exc_allow,
        )

    async def _load_tools(self, state: Optional[ExecutionState] = None) -> List[Any]:
        """
        Создаёт tools из inline конфигов.
        
        Иерархия resources для tools как у CodeNode: flow → node → tool (правее сильнее).
        """
        container = get_container()
        
        flow_resources: Dict[str, Any] = {}
        skill_resources: Dict[str, Any] = {}
        if state is not None:
            fr, sr = await container.flow_factory.get_resource_maps(
                state.session_flow_id,
                state.branch_id,
                state.flow_config_version,
            )
            flow_resources = fr or {}
            skill_resources = dict(sr) if sr else {}
        node_resources_cfg = self.config.get("resources", {}) or {}
        merged_node_level = {**flow_resources, **skill_resources, **node_resources_cfg}
        
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

class CodeNode(BaseNode):
    """
    Универсальная нода для выполнения кода.
    
    Поддерживает разные языки (python, javascript, go).
    Только runner.execute_tool(code, args, state) по строке ``code`` из конфига;
    ``tool_id`` — идентификатор для UI/ссылок, не путь к FunctionTool в процессе.
    """

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        cfg = self.config
        
        self.language = cfg.get("language", "python")
        self.code = cfg.get("code")
        self.tool_id = cfg.get("tool_id")
        self.args_schema = cfg.get("args_schema")
        
        self._runner = None
        
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
        Выполняет только inline ``code`` через runner.execute_tool(code, args, state).
        """
        if not self.code or not str(self.code).strip():
            raise ValueError(
                f"Node '{self.node_id}': требуется непустой inline code (tool_id без кода не исполняется)"
            )

        args = self._build_args(inputs)
        logger.info(f"[node:{self.node_id}] execute_tool с args: {list(args.keys())}")

        resources = await self._resolve_resources(state)
        runner = self._get_runner(resources=resources)
        return await runner.execute_tool(self.code, args, state)

    def _build_args(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Формирует args из inputs с учетом defaults из args_schema."""
        args = {}
        
        if self.args_schema:
            for name, schema in self.args_schema.items():
                if "default" in schema:
                    args[name] = schema["default"]
        
        args.update(inputs)
        return args


class FlowNode(BaseNode):
    """Вложенный Flow с поддержкой skill."""

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        cfg = self.config
        inner = cfg.get("config")
        if not isinstance(inner, dict):
            inner = {}
        r_f = cfg.get("flow_id")
        i_f = inner.get("flow_id")
        if isinstance(r_f, str) and r_f.strip():
            self.flow_id = r_f
        elif isinstance(i_f, str) and i_f.strip():
            self.flow_id = i_f
        else:
            self.flow_id = None
        r_s = cfg.get("branch_id")
        i_s = inner.get("branch_id")
        if isinstance(r_s, str) and r_s.strip():
            self.branch_id = r_s
        elif isinstance(i_s, str) and i_s.strip():
            self.branch_id = i_s
        else:
            self.branch_id = "default"
        self._nested_flow = None

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """
        Запускает вложенный Flow.
        
        _copy_state_back мержит изменения из вложенного flow обратно в state.
        """
        if not self.flow_id:
            raise ValueError(f"Node '{self.node_id}': flow_id required")

        nested_state = self._prepare_state(state, inputs)

        if self._nested_flow is None:
            container = get_container()
            self._nested_flow = await container.flow_factory.get_flow(self.flow_id, self.branch_id)

        result = await self._nested_flow.run(nested_state)
        self._copy_state_back(result, state, full_trust=False)

        return state.response


class RemoteFlowNode(BaseNode):
    """Внешний flow по A2A протоколу."""

    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        cfg = self.config
        
        self.url = cfg.get("url")
        self.remote_registry_flow_id = cfg.get("flow_id")
        self.branch_id = cfg.get("branch_id", "default")
        self.auth_headers_config = cfg.get("auth_headers", {})

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """Вызывает внешний flow по A2A."""
        if not self.url and not self.remote_registry_flow_id:
            raise ValueError("RemoteFlowNode requires 'url' or 'flow_id'")

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
            branch_id=self.branch_id,
            auth_headers=auth_headers,
        )

        if not isinstance(result, dict):
            raise ValueError(
                f"RemoteFlowNode: ожидался dict от a2a_client.send_task, получено {type(result)}"
            )
        if "response" not in result:
            raise ValueError("RemoteFlowNode: ответ A2A без обязательного поля 'response'")
        if "status" not in result:
            raise ValueError("RemoteFlowNode: ответ A2A без обязательного поля 'status'")

        state.response = result["response"]
        setattr(state, "remote_status", result["status"])
        return result["response"]

    async def _resolve_connection(
        self, container, variables: Dict[str, Any]
    ) -> tuple[str, Dict[str, str]]:
        """Резолвит URL и auth headers."""
        if self.remote_registry_flow_id:
            external_flow = await container.flow_discovery.get_flow(self.remote_registry_flow_id)
            if external_flow is None:
                raise ValueError(
                    f"External flow '{self.remote_registry_flow_id}' not found in registry"
                )
            return external_flow.url, external_flow.auth_headers
        
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
            if not isinstance(interrupt_data, dict):
                raise ValueError(
                    f"ExternalAPINode: interrupt должен быть dict, получено {type(interrupt_data)}"
                )
            body = parse_interrupt_body_from_external_dict(interrupt_data)
            InterruptManager.apply_interrupt(state, body, tool_call=None)
            return None

        if result.get("status") == "error":
            err = result.get("error")
            if err is None:
                raise ValueError("ExternalAPINode: status=error без поля 'error'")
            raise ValueError(f"External API error: {err}")

        for response_field, state_field in api_cfg.state_mapping.items():
            data = result.get("data", {})
            if isinstance(data, dict) and response_field in data:
                setattr(state, state_field, data[response_field])

        data = result.get("data")
        setattr(state, "api_response", data)
        setattr(state, "api_status", result.get("status"))
        setattr(state, "result", data)

        return data


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
        
        from apps.flows.src.clients.mcp_client import MCPHttpClient
        
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
            "recipient": "@state:triggers.my_telegram.context.chat_id",
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
        
        from apps.flows.src.models.enums import ChannelType
        
        channel_value = cfg.get("channel", "telegram")
        self.channel = ChannelType(channel_value) if isinstance(channel_value, str) else channel_value
        self.action = cfg.get("action", "send_message")
        self.channel_config = cfg.get("channel_config", {})

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        """Отправляет сообщение через channel handler."""
        from apps.flows.src.variables import VariableResolver, VarResolver
        
        container = get_container()
        handler = container.channel_registry.get(self.channel)
        
        # Собираем все переменные (flow, компании, системные)
        all_variables = VariableResolver.resolve_all(local_vars=state.variables)
        
        # Merge channel_config с inputs
        config = {**self.channel_config}
        config = VarResolver.resolve_deep(config, all_variables)
        
        async with traced_operation(
            "flows.channel.execute_action",
            event_type="channel.action",
            operation_category="channel",
            extra_attributes={
                "platform.channel.type": self.channel.value,
                "platform.channel.action": self.action,
            },
        ):
            result = await handler.execute_action(
                action=self.action,
                params=inputs,
                config=config,
                variables=all_variables,
            )
        
        setattr(state, "channel_result", result)
        setattr(state, "result", result)

        logger.info(
            f"[node:{self.node_id}] Channel {self.channel.value} "
            f"action {self.action} completed"
        )

        return result


class HitlNode(BaseNode):
    """
    Нода передачи диалога оператору очереди (персистентная задача + interrupt).
    После complete в очереди: resume с тем же correlation — задача в БД completed,
    нода выставляет response и отдаёт управление следующим нодам по рёбрам.
    """

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        ctx = get_request_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError(
                f"hitl_node {self.node_id}: нужен Context с active_company"
            )
        company_id = ctx.active_company.company_id
        cid_resume = state.hitl_handoff_correlation_id
        if isinstance(cid_resume, str) and cid_resume.strip() and state.content:
            repo = get_container().operator_repository
            existing_resume = await repo.get_task_by_correlation(
                company_id, cid_resume.strip()
            )
            if existing_resume is None:
                raise ValueError(
                    f"hitl_node {self.node_id}: resume с correlation_id={cid_resume!r}, "
                    "задача оператора не найдена"
                )
            if existing_resume.status != OperatorTaskStatus.COMPLETED.value:
                raise ValueError(
                    f"hitl_node {self.node_id}: задача оператора ещё не завершена "
                    f"(status={existing_resume.status!r})"
                )
            state.hitl_handoff_correlation_id = None
            answer = str(state.content).strip()
            state.response = answer
            return None

        slug_in = inputs.get("assignee_queue")
        slug_cfg = self.config.get("operator_queue_slug")
        qid_cfg = self.config.get("operator_queue_id")

        slug_effective: Optional[str] = None
        if isinstance(slug_in, str) and slug_in.strip():
            slug_effective = slug_in.strip()
        elif isinstance(slug_cfg, str) and slug_cfg.strip():
            slug_effective = slug_cfg.strip()
        elif isinstance(qid_cfg, str) and qid_cfg.strip():
            row = await get_container().operator_repository.get_queue_by_id(
                company_id, qid_cfg.strip()
            )
            if row is None:
                raise ValueError(
                    f"hitl_node {self.node_id}: очередь {qid_cfg!r} не найдена"
                )
            slug_effective = row.slug
        else:
            raise ValueError(
                f"hitl_node {self.node_id}: укажите operator_queue_slug, operator_queue_id "
                "или input_mapping.assignee_queue"
            )

        title = inputs.get("task_title") or self.config.get("operator_task_title")
        if not title or not str(title).strip():
            raise ValueError(
                f"hitl_node {self.node_id}: нужен task_title (input_mapping или operator_task_title)"
            )
        message = (
            inputs.get("user_facing_message")
            or inputs.get("question")
            or self.config.get("operator_user_message")
        )
        if not message or not str(message).strip():
            raise ValueError(
                f"hitl_node {self.node_id}: нужен текст для пользователя "
                "(user_facing_message / question / operator_user_message)"
            )

        raw_mode = (
            inputs.get("handoff_mode")
            or self.config.get("operator_handoff_mode")
            or "single_reply"
        )
        mode = HandoffMode(str(raw_mode).strip())

        svc = get_container().operator_handoff_service
        cid, op_task_id = await svc.register_handoff(
            state,
            question=str(message).strip(),
            task_title=str(title).strip(),
            assignee_queue_slug=slug_effective,
            handoff_mode=mode,
        )
        raise FlowInterrupt(
            body=OperatorTaskInterrupt(
                question=str(message).strip(),
                task_title=str(title).strip(),
                assignee_queue=slug_effective,
                handoff_mode=mode,
                operator_task_id=op_task_id,
            ),
            correlation_id=cid,
        )


class ResourceNode(BaseNode):
    """
    Нода-ресурс на графе: позиция на канве и привязка записей resources у ноды.
    Рантайм не вызывает LLM и не мутирует state; merge ресурсов при использовании
    остаётся на ResourceResolver у исполняемых нод и tools.
    """

    name = "resource"

    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> None:
        return None


def _infer_node_type_from_fields(node_config: Dict[str, Any]) -> None:
    """
    Выставляет type по полям, если type отсутствует (частичные данные в БД / мердж веток).
    """
    if node_config.get("type"):
        return
    code = node_config.get("code")
    if isinstance(code, str) and code.strip():
        node_config["type"] = NodeType.CODE.value
        return
    fn = node_config.get("function")
    if isinstance(fn, str) and fn.strip():
        node_config["type"] = NodeType.CODE.value
        return
    if node_config.get("server_id") and node_config.get("tool_name"):
        node_config["type"] = NodeType.MCP.value
        return
    if node_config.get("operator_queue_slug") or node_config.get("operator_queue_id"):
        node_config["type"] = NodeType.HITL_NODE.value
        return
    ch = node_config.get("channel")
    if ch is not None and ch != "":
        node_config["type"] = NodeType.CHANNEL.value
        return
    url = node_config.get("url")
    if isinstance(url, str) and url.strip():
        if node_config.get("method"):
            node_config["type"] = NodeType.EXTERNAL_API.value
        else:
            node_config["type"] = NodeType.REMOTE_FLOW.value
        return
    if node_config.get("flow_id"):
        node_config["type"] = NodeType.FLOW.value
        return
    if node_config.get("llm") is not None or node_config.get("llm_override") is not None:
        node_config["type"] = NodeType.LLM_NODE.value
        return
    prompt = node_config.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        node_config["type"] = NodeType.LLM_NODE.value
        return


async def create_node(node_id: str, node_config: Dict[str, Any]) -> BaseNode:
    """
    Создаёт ноду через NodeRegistry.
    
    Zero-Guess: неизвестный тип = исключение.
    """
    node_config = dict(node_config)
    t = node_config.get("type")
    if isinstance(t, str) and not t.strip():
        node_config.pop("type", None)

    if not node_config.get("type"):
        if not (isinstance(node_config.get("code"), str) and node_config.get("code", "").strip()):
            tool_id = node_config.get("tool_id")
            if tool_id:
                container = get_container()
                stored = await container.tool_repository.get(str(tool_id))
                if stored is not None:
                    c = getattr(stored, "code", None)
                    if isinstance(c, str) and c.strip():
                        node_config["code"] = c
        _infer_node_type_from_fields(node_config)

    node_type_value = node_config.get("type")
    if not node_type_value:
        keys = sorted(node_config.keys())
        raise ValueError(
            f"Node '{node_id}': type is required (поля: {keys})"
        )
    
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
