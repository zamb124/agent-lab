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
import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar, Literal, TypeAlias, cast, overload, override

from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.clients.external_api_client import ExternalAPIClient
from apps.flows.src.clients.mcp_client import MCPHttpClient
from apps.flows.src.container_contracts import FlowRuntimeContainer, RuntimeFlowProtocol
from apps.flows.src.container_state import get_current_container
from apps.flows.src.mapping import MappingResolver
from apps.flows.src.mock.resolver import get_mock_for_node
from apps.flows.src.models import (
    NodeConfig,
    NodeLLMConfig,
    ReactConfig,
    ResourceReference,
    ResourceReferenceInput,
)
from apps.flows.src.models.enums import ChannelType, NodeType
from apps.flows.src.models.exception_absorb_allow import ExceptionAbsorbAllowName
from apps.flows.src.models.external_api import ExternalAPIConfig, HTTPMethod
from apps.flows.src.models.operator_schemas import OperatorTaskStatus
from apps.flows.src.runtime.effective_llm_config import resolve_effective_llm_config_for_node
from apps.flows.src.runtime.exception_policy import node_exception_policy, should_absorb_exception
from apps.flows.src.runtime.exceptions import BreakpointInterrupt, FlowInterrupt
from apps.flows.src.runtime.llm_context_memory import resolve_memory_context_source_for_runtime
from apps.flows.src.runtime.llm_context_rag import resolve_rag_context_source_registry_for_runtime
from apps.flows.src.runtime.llm_context_resource import resolve_llm_context_policy_for_runtime
from apps.flows.src.runtime.llm_override_params import client_kwargs_from_llm_config
from apps.flows.src.runtime.llm_resource_override import (
    infer_unique_llm_resource_key_from_merged_maps,
    resolve_llm_config_with_resource_key,
)
from apps.flows.src.runtime.runners import LlmNodeRunner
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.registry import ToolMaterializeInput, ToolRegistry
from apps.flows.src.variables import VariableResolver, VarResolver
from core.clients.llm import get_llm
from core.context import get_context as get_request_context
from core.errors import NodeWallClockTimeoutError
from core.llm_context import (
    LLMContextPatch,
    LLMContextProfile,
    LLMContextSource,
    LLMContextSourceRegistry,
)
from core.logging import get_logger
from core.state import (
    ExecutionExceptionRecord,
    ExecutionState,
    parse_interrupt_body_from_external_dict,
)
from core.state.interrupt import HandoffMode, OperatorTaskInterrupt
from core.state.mutation_policy import (
    forbid_frozen_update_key,
    should_skip_field_on_user_returned_state_copy,
)
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, require_json_object, require_json_value

logger = get_logger(__name__)
NodeInputs: TypeAlias = JsonObject
NodeRunResult: TypeAlias = ExecutionState | JsonValue


def _config_mapping(config: JsonObject, field_name: str) -> JsonObject | None:
    if field_name not in config or config[field_name] is None:
        return None
    value = config[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name}: ожидается object")
    return require_json_object(value, field_name)


def _config_mapping_default(config: JsonObject, field_name: str) -> JsonObject:
    value = _config_mapping(config, field_name)
    if value is None:
        return {}
    return value


def _config_string_map(config: JsonObject, field_name: str) -> dict[str, str] | None:
    value = _config_mapping(config, field_name)
    if value is None:
        return None
    out: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise ValueError(f"{field_name}.{key}: ожидается строка")
        out[key] = item
    return out


def _config_string_map_default(config: JsonObject, field_name: str) -> dict[str, str]:
    value = _config_string_map(config, field_name)
    if value is None:
        return {}
    return value


def _config_optional_string(config: JsonObject, field_name: str) -> str | None:
    if field_name not in config or config[field_name] is None:
        return None
    value = config[field_name]
    if not isinstance(value, str):
        raise ValueError(f"{field_name}: ожидается строка")
    return value


def _config_string(config: JsonObject, field_name: str, default: str) -> str:
    value = _config_optional_string(config, field_name)
    if value is None:
        return default
    return value


def _config_bool(config: JsonObject, field_name: str, default: bool) -> bool:
    if field_name not in config or config[field_name] is None:
        return default
    value = config[field_name]
    if not isinstance(value, bool):
        raise ValueError(f"{field_name}: ожидается bool")
    return value


def _config_float(config: JsonObject, field_name: str, default: float) -> float:
    if field_name not in config or config[field_name] is None:
        return default
    value = config[field_name]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name}: ожидается number")
    return float(value)


def _config_json_object(
    config: JsonObject,
    field_name: str,
) -> JsonObject | None:
    value = _config_mapping(config, field_name)
    if value is None:
        return None
    return value


def _config_messages_filter(
    config: JsonObject,
    field_name: str,
) -> Literal["all", "own"] | list[str]:
    if field_name not in config or config[field_name] is None:
        return "all"
    value = config[field_name]
    if value in ("all", "own"):
        return value
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{field_name}: список должен содержать непустые строки")
            out.append(item)
        return out
    raise ValueError(f"{field_name}: ожидается 'all', 'own' или list[str]")


def _config_tool_refs(config: JsonObject, field_name: str) -> list[str | ToolMaterializeInput]:
    if field_name not in config or config[field_name] is None:
        return []
    value = config[field_name]
    if not isinstance(value, list):
        raise ValueError(f"{field_name}: ожидается list")
    out: list[str | ToolMaterializeInput] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            out.append(require_json_object(item, f"{field_name}[]"))
            continue
        raise ValueError(f"{field_name}: ожидается string или object")
    return out


def _config_args_schema(config: JsonObject) -> dict[str, JsonObject] | None:
    value = _config_mapping(config, "args_schema")
    if value is None:
        return None
    out: dict[str, JsonObject] = {}
    for arg_name, schema in value.items():
        if not isinstance(schema, Mapping):
            raise ValueError(f"args_schema.{arg_name}: ожидается object")
        out[arg_name] = require_json_object(schema, f"args_schema.{arg_name}")
    return out


def _config_resource_refs(config: JsonObject, field_name: str = "resources") -> dict[str, ResourceReferenceInput]:
    raw = _config_mapping_default(config, field_name)
    out: dict[str, ResourceReferenceInput] = {}
    for resource_key, resource_value in raw.items():
        if not isinstance(resource_value, Mapping):
            raise ValueError(f"{field_name}.{resource_key}: ожидается object")
        out[resource_key] = require_json_object(
            resource_value,
            f"{field_name}.{resource_key}",
        )
    return out


class NodeRunMethod:
    """Callable wrapper для node.run() с поддержкой .kiq()"""

    def __init__(self, node: BaseNode):
        self._node: BaseNode = node

    async def __call__(self, state: ExecutionState) -> ExecutionState:
        """Прямой вызов в текущем процессе."""
        return await self._node.execute(state)

    async def kiq(self, state: ExecutionState) -> ExecutionState:
        """TaskIQ dispatch lives at the task/API boundary, not inside runtime nodes."""
        _ = state
        raise RuntimeError("node.run.kiq() is not part of runtime; use execute_node task at the boundary")


class NodeRunDescriptor:
    """Descriptor для node.run"""

    @overload
    def __get__(
        self,
        obj: None,
        objtype: type[BaseNode] | None = None,
    ) -> NodeRunDescriptor: ...

    @overload
    def __get__(
        self,
        obj: BaseNode,
        objtype: type[BaseNode] | None = None,
    ) -> NodeRunMethod: ...

    def __get__(
        self,
        obj: BaseNode | None,
        objtype: type[BaseNode] | None = None,
    ) -> NodeRunDescriptor | NodeRunMethod:
        if obj is None:
            return self
        return NodeRunMethod(obj)


class BaseNode(ABC):
    """
    Базовый класс для нод. Node = функция ExecutionState -> ExecutionState.

    Template Method паттерн:
    - run(state) или run.kiq(state) - единая точка входа для всех нод
    - _resolve_inputs() - единообразный резолвинг input_mapping
    - get_filtered_messages() - фильтрация messages
    - _run_impl() - конкретная логика каждой ноды

    Конфигурация:
    - input_mapping: Dict - маппинг входных данных из state
    - output_mapping: Dict[str, str] - маппинг полей результата -> state fields
    - save_to_messages: bool - добавлять результат в messages
    - message_field: str - какое поле писать в messages (по умолчанию diff стейта)
    - messages_filter: "all" / "own" / List[str] — срез по metadata.node_id

    Контракт _run_impl() для ВСЕХ нод:
    - Возвращает JSON-значение или ExecutionState
    - dict: поля записываются в state через output_mapping
    - не dict и не None: записывается в state.result
    - None: ничего не записывается
    """

    name: ClassVar[str] = "node"
    description: ClassVar[str | None] = None
    node_type: ClassVar[NodeType | None] = None

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        self.node_id: str = node_id
        self.config: JsonObject = dict(config) if config is not None else {}
        if self.node_type is not None and not self.config.get("type"):
            self.config = {**self.config, "type": self.node_type.value}
        self.container: FlowRuntimeContainer | None = container or get_current_container()
        self.input_mapping: JsonObject | None = _config_mapping(self.config, "input_mapping")
        self.output_mapping: dict[str, str] | None = _config_string_map(self.config, "output_mapping")
        self.save_to_messages: bool = _config_bool(self.config, "save_to_messages", False)
        self.message_field: str | None = _config_optional_string(self.config, "message_field")
        self.messages_filter: Literal["all", "own"] | list[str] = _config_messages_filter(
            self.config,
            "messages_filter",
        )

    @classmethod
    def from_config(
        cls,
        node_id: str,
        config: JsonObject,
        *,
        container: FlowRuntimeContainer | None = None,
    ) -> "BaseNode":
        """Создает ноду из конфига."""
        return cls(node_id=node_id, config=config, container=container)

    def _check_mock(self, state: ExecutionState) -> JsonObject | None:
        """Проверяет наличие mock для ноды."""
        return get_mock_for_node(state, self.node_id)

    def _resolve_inputs(self, state: ExecutionState) -> NodeInputs:
        """
        Единообразный резолвинг input_mapping для всех типов нод.

        Returns:
            Dict с резолвнутыми значениями из input_mapping
        """
        if not self.input_mapping:
            return {}
        return require_json_object(
            MappingResolver.build_mapped_state(self.input_mapping, state),
            f"node.{self.node_id}.input_mapping",
        )

    def get_filtered_messages(self, state: ExecutionState) -> list[Message]:
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

        allowed = set(self.messages_filter)
        return [
            m for m in all_messages
            if self._get_message_node_id(m) in allowed
        ]

    def _get_filtered_messages(self, state: ExecutionState) -> list[Message]:
        return self.get_filtered_messages(state)

    def _append_to_messages(self, state: ExecutionState, result: NodeRunResult) -> None:
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
    def _get_message_node_id(msg: Message) -> str | None:
        """Извлекает node_id из metadata сообщения."""
        metadata = require_json_object(msg.metadata or {}, "message.metadata")
        node_id = metadata.get("node_id")
        return node_id if isinstance(node_id, str) else None

    # Descriptor для унифицированного вызова: node.run(state) или node.run.kiq(state)
    run: ClassVar[NodeRunDescriptor] = NodeRunDescriptor()

    async def execute(self, state: ExecutionState) -> ExecutionState:
        """
        Выполняет ноду в текущем процессе.

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

        state_before: JsonObject | None = None
        if self.save_to_messages and not self.message_field:
            state_before = require_json_object(
                state.model_dump(mode="json", exclude_none=False),
                "state_before",
            )

        inputs = self._resolve_inputs(state)

        node_timeout = self.config.get("node_timeout_seconds")
        nto: int | None = None
        try:
            if node_timeout is not None:
                if isinstance(node_timeout, bool) or not isinstance(node_timeout, int):
                    raise ValueError("node_timeout_seconds: ожидается integer")
                nto = node_timeout
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
            exception_result: JsonObject = {
                "error": True,
                "error_type": type(e).__name__,
                "message": str(e),
            }
            result = exception_result

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

    def _apply_output_mapping(self, state: ExecutionState, result: JsonValue) -> None:
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
        self,
        state: ExecutionState,
        state_before: JsonObject | None,
        result: NodeRunResult | None,
    ) -> str | None:
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
        self,
        state_before: JsonObject,
        state_after: ExecutionState,
    ) -> str | None:
        """Вычисляет diff между состояниями для записи в messages."""
        state_after_dict = require_json_object(
            state_after.model_dump(mode="json", exclude_none=False),
            "state_after",
        )

        skip_fields = {"messages", "prompt_history", "node_history", "nested_states"}

        diff_parts: list[str] = []
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
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
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

        extra_src = require_json_object(
            source.__pydantic_extra__ or {},
            "source.extra",
        )
        if extra_src:
            if not hasattr(target, "__pydantic_extra__") or target.__pydantic_extra__ is None:
                target.__pydantic_extra__ = {}
            if full_trust:
                target.__pydantic_extra__.update(extra_src)
            else:
                for ek, ev in extra_src.items():
                    if should_skip_field_on_user_returned_state_copy(ek):
                        continue
                    target.__pydantic_extra__[ek] = ev

    def _prepare_state(self, state: ExecutionState, inputs: NodeInputs) -> ExecutionState:
        """
        Создает state для вложенного выполнения.
        Применяет inputs и фильтрует messages.
        Сбрасывает current_nodes чтобы вложенный flow начал со своего entry.
        """
        new_state = ExecutionState.model_validate(state.model_dump(exclude_none=False))

        for key, value in inputs.items():
            setattr(new_state, key, value)

        new_state.messages = self.get_filtered_messages(state)

        # Сбрасываем current_nodes — вложенный flow начнёт со своего entry
        new_state.current_nodes = []
        object.__setattr__(new_state, "_skip_hot_state_checkpoint", True)

        return new_state

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
    name: ClassVar[str] = "llm_node"
    node_type: ClassVar[NodeType | None] = NodeType.LLM_NODE
    description: ClassVar[str | None] = None
    prompt: ClassVar[str | None] = None
    tools: ClassVar[list[BaseTool]] = []

    def __init__(
        self,
        node_id: str | None = None,
        config: JsonObject | None = None,
        node_config: NodeConfig | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        super().__init__(node_id or self.name, config, container=container)
        cfg = self.config

        self.prompt_template: str = self.prompt or _config_string(cfg, "prompt", "")
        self.tool_refs: list[str | ToolMaterializeInput] = _config_tool_refs(cfg, "tools")
        raw_llm = cfg.get("llm")
        raw_legacy_llm = cfg.get("llm_override")
        if isinstance(raw_legacy_llm, dict) and raw_legacy_llm:
            self.llm_config_dict: JsonObject = require_json_object(raw_legacy_llm, "llm_override")
        elif isinstance(raw_llm, dict):
            self.llm_config_dict = require_json_object(raw_llm, "llm")
        else:
            self.llm_config_dict = {}

        self._node_config: NodeConfig | None = node_config
        self._runner: LlmNodeRunner | None = None
        self._loaded_tools: list[BaseTool] | None = None
        if node_config is not None:
            self.messages_filter: Literal["all", "own"] | list[str] = node_config.messages_filter

    def _prepare_llm_runner_state(
        self, state: ExecutionState, inputs: NodeInputs
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
    def llm_config(self) -> JsonObject:
        """LLM конфигурация."""
        return self.llm_config_dict

    def _get_typed_llm_config(self) -> NodeLLMConfig | None:
        if self._node_config and self._node_config.llm:
            return self._node_config.llm
        if not self.llm_config_dict:
            return None
        return NodeLLMConfig.model_validate(self.llm_config_dict)

    @property
    def llm_node_name(self) -> str:
        """Название ноды"""
        if self._node_config:
            return self._node_config.name
        return self.name

    @property
    def llm_node_description(self) -> str | None:
        """Описание ноды"""
        if self._node_config and self._node_config.description:
            return self._node_config.description
        return self.description

    @property
    def llm_node_prompt(self) -> str | None:
        """Промпт ноды"""
        if self._node_config and self._node_config.prompt:
            return self._node_config.prompt
        return self.prompt_template or self.prompt

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
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
        input_data: JsonObject = {"content": content}

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
            structured_payload = require_json_value(
                cast(JsonValue, structured_result),
                "state.structured_output_result",
            )
            state.response = json.dumps(structured_payload, ensure_ascii=False)
            return structured_payload

        return {"response": state.response} if state.response else None

    async def get_runner(self, state: ExecutionState | None = None) -> LlmNodeRunner:
        """Возвращает runner для LlmNode."""
        if self._runner is not None:
            return self._runner

        tools = await self.get_tools(state)
        prompt = self.llm_node_prompt or ""

        base = self._node_config or self._create_default_config()
        config = await self._resolve_effective_node_config(base, state)
        llm_context_policy = await self._resolve_effective_llm_context_policy(config, state)
        llm_context_source_registry = await self._resolve_llm_context_source_registry(
            config,
            state,
            llm_context_policy,
        )

        self._runner = LlmNodeRunner(
            node_config=config,
            tools=tools,
            llm=None,
            prompt=prompt,
            llm_node=self,
            container=self.container,
            llm_context_policy=llm_context_policy,
            llm_context_source_registry=llm_context_source_registry,
        )

        return self._runner

    async def get_tools(self, state: ExecutionState | None = None) -> list[BaseTool]:
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

    async def set_tools(self, tools: list[BaseTool]) -> None:
        """Устанавливает tools."""
        self._loaded_tools = tools

    def _get_llm(self, state: ExecutionState | None = None):
        """Возвращает company-aware LLM client для legacy вызовов.

        Основной runtime создаёт client внутри runner-а из той же effective config,
        чтобы биллинг и фактический вызов использовали один источник истины.
        """
        base = self._node_config or self._create_default_config()
        effective = resolve_effective_llm_config_for_node(base)
        client_kwargs = client_kwargs_from_llm_config(effective.config, state)
        _ = client_kwargs.setdefault("extra_request_headers", None)
        logger.info(
            "[_get_llm] node_id=%s provider=%s model=%s source=%s",
            self.node_id,
            effective.config.provider,
            effective.config.model,
            effective.source,
        )
        return get_llm(state=state, **client_kwargs)

    async def _resolve_effective_node_config(
        self, base: NodeConfig, state: ExecutionState | None
    ) -> NodeConfig:
        llm_config = base.llm
        if not llm_config:
            return base
        explicit = llm_config.llm_resource_key and str(llm_config.llm_resource_key).strip()
        if state is None:
            if explicit:
                raise ValueError("ExecutionState обязателен при заданном llm_resource_key")
            return base
        container = self.container
        if container is None:
            if explicit or _config_resource_refs(self.config):
                raise RuntimeError(f"LLM node '{self.node_id}' requires FlowContainer to resolve LLM resources")
            return base
        flow_resources, skill_resources = await container.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        node_resources_raw = _config_resource_refs(self.config)
        repo = container.resource_repository
        if explicit:
            merged_ov = await resolve_llm_config_with_resource_key(
                llm_config=llm_config,
                flow_resources=flow_resources or {},
                skill_resources=skill_resources,
                node_resources_raw=node_resources_raw,
                repository=repo,
            )
            return base.model_copy(update={"llm": merged_ov})
        inferred = await infer_unique_llm_resource_key_from_merged_maps(
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            repository=repo,
        )
        if inferred is None:
            return base
        ov_with_key = llm_config.model_copy(update={"llm_resource_key": inferred})
        merged_ov = await resolve_llm_config_with_resource_key(
            llm_config=ov_with_key,
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            repository=repo,
        )
        return base.model_copy(update={"llm": merged_ov})

    async def _resolve_effective_llm_context_policy(
        self,
        base: NodeConfig,
        state: ExecutionState | None,
    ) -> LLMContextProfile:
        node_resources_raw: dict[str, ResourceReferenceInput] = dict(base.resources or {})
        if not node_resources_raw:
            node_resources_raw = _config_resource_refs(self.config)
        explicit = bool(
            base.llm_context_resource_key
            and str(base.llm_context_resource_key).strip()
        )
        has_node_resources = bool(node_resources_raw)
        if state is None:
            if explicit or has_node_resources:
                raise ValueError("ExecutionState обязателен для LLM context resources")
            return await resolve_llm_context_policy_for_runtime(
                llm_context_resource_key=None,
                flow_resources={},
                skill_resources=None,
                node_resources_raw={},
                repository=None,
                node=base.llm_context,
            )

        container = self.container
        if container is None:
            if explicit or has_node_resources:
                raise RuntimeError(
                    f"LLM node '{self.node_id}' requires FlowContainer to resolve LLM context resources"
                )
            return await resolve_llm_context_policy_for_runtime(
                llm_context_resource_key=None,
                flow_resources={},
                skill_resources=None,
                node_resources_raw={},
                repository=None,
                node=base.llm_context,
            )

        flow_resources, skill_resources = await container.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        return await resolve_llm_context_policy_for_runtime(
            llm_context_resource_key=base.llm_context_resource_key,
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            repository=container.resource_repository,
            node=base.llm_context,
        )

    async def _resolve_llm_context_source_registry(
        self,
        base: NodeConfig,
        state: ExecutionState | None,
        policy: LLMContextProfile,
    ) -> LLMContextSourceRegistry | None:
        if policy.mode == "off" or policy.retrieval.mode == "off":
            return None

        node_resources_raw: dict[str, ResourceReferenceInput] = dict(base.resources or {})
        if not node_resources_raw:
            node_resources_raw = _config_resource_refs(self.config)
        has_node_resources = bool(node_resources_raw)
        if state is None:
            if has_node_resources:
                raise ValueError("ExecutionState обязателен для LLM context RAG resources")
            return None

        container = self.container
        if container is None:
            if has_node_resources:
                raise RuntimeError(
                    f"LLM node '{self.node_id}' requires FlowContainer to resolve RAG context resources"
                )
            return None

        flow_resources, skill_resources = await container.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        sources: list[LLMContextSource] = []
        memory_source = resolve_memory_context_source_for_runtime(
            store=container.llm_context_memory_store,
            state=state,
            node_id=self.node_id,
        )
        if memory_source is not None:
            sources.append(memory_source)

        rag_registry = await resolve_rag_context_source_registry_for_runtime(
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            resource_repository=container.resource_repository,
            rag_repository=container.rag_repository,
            state=state,
        )
        if rag_registry is not None:
            sources.extend(rag_registry.sources)
        if not sources:
            return None
        return LLMContextSourceRegistry(sources)

    def _create_default_config(self) -> NodeConfig:
        """Создает конфигурацию по умолчанию."""
        llm_config = None
        if self.llm_config_dict:
            allowed = set(NodeLLMConfig.model_fields.keys())
            raw_llm = {k: v for k, v in self.llm_config_dict.items() if k in allowed}
            llm_config = NodeLLMConfig.model_validate(raw_llm)

        react_config = None
        react_dict = _config_mapping(self.config, "react")
        if react_dict:
            react_config = ReactConfig.model_validate(react_dict)

        structured_output = _config_bool(self.config, "structured_output", False)
        output_schema = _config_json_object(self.config, "output_schema")
        messages_filter = _config_messages_filter(self.config, "messages_filter")
        llm_context = None
        llm_context_raw = self.config.get("llm_context") if self.config else None
        if llm_context_raw is not None:
            llm_context = LLMContextPatch.model_validate(llm_context_raw)
        llm_context_resource_key = _config_optional_string(
            self.config,
            "llm_context_resource_key",
        )

        exc_response = False
        exc_allow: list[ExceptionAbsorbAllowName] = []
        if self.config:
            if "exception_as_response" in self.config:
                exc_response = bool(self.config["exception_as_response"])
            raw_allow = self.config.get("exception_allow_types")
            if raw_allow is not None:
                if not isinstance(raw_allow, list):
                    raise ValueError("exception_allow_types: ожидается list[str]")
                exc_allow = [ExceptionAbsorbAllowName(str(item)) for item in raw_allow]
        resources = {
            key: ResourceReference.model_validate(value)
            for key, value in _config_resource_refs(self.config).items()
        }

        return NodeConfig(
            node_id=self.node_id,
            type=NodeType.LLM_NODE,
            name=self.node_id,
            description=self.description or "",
            prompt=self.prompt_template or self.prompt or "",
            llm=llm_config,
            llm_context=llm_context,
            llm_context_resource_key=llm_context_resource_key,
            resources=resources,
            react=react_config,
            structured_output=structured_output,
            output_schema=output_schema,
            messages_filter=messages_filter,
            exception_as_response=exc_response,
            exception_allow_types=exc_allow,
        )

    async def _load_tools(self, state: ExecutionState | None = None) -> list[BaseTool]:
        """
        Создаёт tools из inline конфигов.

        Code tools execute in isolated runners. Platform access goes through
        capability-gateway, so resources are not injected into tool namespaces.
        """
        _ = state
        container = self.container
        if container is None:
            registry = ToolRegistry()
            return await registry.create_tools(self.tool_refs)

        return await container.tool_registry.create_tools(self.tool_refs)

    async def before_prompt_render(
        self, prompt_template: str, state: ExecutionState, variables: JsonObject
    ) -> tuple[str, JsonObject]:
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
        _ = state
        return prompt_template, variables

    async def after_prompt_render(
        self, rendered_prompt: str, state: ExecutionState
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
        _ = state
        return rendered_prompt

class CodeNode(BaseNode):
    """
    Универсальная нода для выполнения кода.

    Поддерживает разные языки (python, javascript, go).
    Только function-entrypoint через runner.execute_tool(code, args, state) по строке ``code`` из конфига;
    ``tool_id`` — идентификатор для UI/ссылок, не путь к FunctionTool в процессе.
    """

    node_type: ClassVar[NodeType | None] = NodeType.CODE

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        super().__init__(node_id, config, container=container)
        cfg = self.config

        self.language: str = _config_string(cfg, "language", "python")
        raw_entrypoint = cfg.get("entrypoint")
        self.entrypoint: str | None = raw_entrypoint.strip() if isinstance(raw_entrypoint, str) and raw_entrypoint.strip() else None
        raw_code = cfg.get("code")
        self.code: str | None = raw_code if isinstance(raw_code, str) else None
        raw_tool_id = cfg.get("tool_id")
        self.tool_id: str | None = raw_tool_id if isinstance(raw_tool_id, str) else None
        self.args_schema: dict[str, JsonObject] | None = _config_args_schema(cfg)

    def _get_runner(self):
        """Возвращает isolated runner для текущего языка."""
        container = self.container
        if container is None:
            raise RuntimeError(f"Code node '{self.node_id}' requires FlowContainer to create remote code runner")
        return container.get_code_runner(self.language)

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """
        Выполняет только inline ``code`` через runner.execute_tool(code, args, state).
        """
        if not self.code or not str(self.code).strip():
            raise ValueError(
                f"Node '{self.node_id}': требуется непустой inline code (tool_id без кода не исполняется)"
            )
        if self.config.get("resources"):
            raise ValueError(
                f"Code node '{self.node_id}': resources are not injected into sandbox code. "
                + "Use capability('tools.call', ...) / Capability('tools.call', ...) or a dedicated platform capability."
            )

        args = self._build_args(inputs)
        logger.info(f"[node:{self.node_id}] execute_tool с args: {list(args.keys())}")

        runner = self._get_runner()
        return await runner.execute_tool(self.code, args, state, entrypoint=self.entrypoint)

    def _build_args(self, inputs: NodeInputs) -> JsonObject:
        """Формирует args из inputs с учетом defaults из args_schema."""
        args: JsonObject = {}

        if self.args_schema:
            for name, schema in self.args_schema.items():
                if "default" in schema:
                    args[name] = schema["default"]

        args.update(inputs)
        return args


class FlowNode(BaseNode):
    """Вложенный Flow с поддержкой skill."""

    node_type: ClassVar[NodeType | None] = NodeType.FLOW

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        super().__init__(node_id, config, container=container)
        cfg = self.config
        inner = cfg.get("config")
        if not isinstance(inner, dict):
            inner = {}
        r_f = cfg.get("flow_id")
        i_f = inner.get("flow_id")
        if isinstance(r_f, str) and r_f.strip():
            self.flow_id: str | None = r_f
        elif isinstance(i_f, str) and i_f.strip():
            self.flow_id = i_f
        else:
            self.flow_id = None
        r_s = cfg.get("branch_id")
        i_s = inner.get("branch_id")
        if isinstance(r_s, str) and r_s.strip():
            self.branch_id: str = r_s
        elif isinstance(i_s, str) and i_s.strip():
            self.branch_id = i_s
        else:
            self.branch_id = "default"
        self._nested_flow: RuntimeFlowProtocol | None = None

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """
        Запускает вложенный Flow.

        _copy_state_back мержит изменения из вложенного flow обратно в state.
        """
        if not self.flow_id:
            raise ValueError(f"Node '{self.node_id}': flow_id required")

        nested_state = self._prepare_state(state, inputs)

        if self._nested_flow is None:
            container = self.container
            if container is None:
                raise RuntimeError(f"Flow node '{self.node_id}' requires FlowContainer to load nested flow")
            self._nested_flow = await container.flow_factory.get_flow(self.flow_id, self.branch_id)
        nested_flow = self._nested_flow
        if nested_flow is None:
            raise ValueError(f"Flow node '{self.node_id}': nested flow '{self.flow_id}' not found")

        result = await nested_flow.run(nested_state)
        self._copy_state_back(result, state, full_trust=False)

        return state.response


class RemoteFlowNode(BaseNode):
    """Внешний flow по A2A протоколу."""

    node_type: ClassVar[NodeType | None] = NodeType.REMOTE_FLOW

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        super().__init__(node_id, config, container=container)
        cfg = self.config

        self.url: str | None = _config_optional_string(cfg, "url")
        self.remote_registry_flow_id: str | None = _config_optional_string(cfg, "flow_id")
        self.branch_id: str = _config_string(cfg, "branch_id", "default")
        self.headers_config: dict[str, str] = _config_string_map_default(cfg, "headers")

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """Вызывает внешний flow по A2A."""
        if not self.url and not self.remote_registry_flow_id:
            raise ValueError("RemoteFlowNode requires 'url' or 'flow_id'")

        container = self.container
        if container is None:
            raise RuntimeError(f"Remote flow node '{self.node_id}' requires FlowContainer to resolve A2A client")

        url, req_headers = await self._resolve_connection(container, state)

        content = inputs.get("content", state.content or "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)

        result = await container.a2a_client.send_task(
            base_url=url,
            content=content,
            session_id=state.session_id,
            branch_id=self.branch_id,
            headers=req_headers,
        )

        result_obj = require_json_object(result, "remote_flow.response")
        if "response" not in result_obj:
            raise ValueError("RemoteFlowNode: ответ A2A без обязательного поля 'response'")
        if "status" not in result_obj:
            raise ValueError("RemoteFlowNode: ответ A2A без обязательного поля 'status'")

        response = result_obj["response"]
        if not isinstance(response, str):
            raise ValueError("RemoteFlowNode: response должен быть строкой")
        state.response = response
        setattr(state, "remote_status", result_obj["status"])
        return response

    async def _resolve_connection(
        self,
        container: FlowRuntimeContainer,
        state: ExecutionState,
    ) -> tuple[str, dict[str, str]]:
        """Резолвит URL и HTTP-заголовки (@state: / @var: в строках)."""
        variables = state.variables
        if self.remote_registry_flow_id:
            external_flow = await container.flow_discovery.get_flow(self.remote_registry_flow_id)
            if external_flow is None:
                raise ValueError(
                    f"External flow '{self.remote_registry_flow_id}' not found in registry"
                )
            external_url = external_flow.url
            if not isinstance(external_url, str) or not external_url.strip():
                raise ValueError(
                    f"External flow '{self.remote_registry_flow_id}' has no valid url"
                )
            return external_url, self._resolve_headers_dict(
                external_flow.headers, state, variables
            )

        url_raw = self.url
        if not isinstance(url_raw, str) or not url_raw.strip():
            raise ValueError("RemoteFlowNode: url must be a non-empty string when flow_id is not set")
        url = MappingResolver.resolve_http_header_value(url_raw, state, variables)
        return url, self._resolve_headers_dict(self.headers_config, state, variables)

    def _resolve_headers_dict(
        self,
        headers: dict[str, str] | None,
        state: ExecutionState,
        variables: JsonObject,
    ) -> dict[str, str]:
        if not headers:
            return {}
        return {
            k: MappingResolver.resolve_http_header_value(v, state, variables)
            for k, v in headers.items()
        }


class ExternalAPINode(BaseNode):
    """Вызов внешнего HTTP API."""

    node_type: ClassVar[NodeType | None] = NodeType.EXTERNAL_API

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        super().__init__(node_id, config, container=container)
        self.api_config: JsonObject = self.config

    def _build_api_config(self) -> ExternalAPIConfig:
        """Строит конфиг API."""
        raw_url = self.api_config.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ValueError(f"ExternalAPINode {self.node_id}: url обязателен")
        return ExternalAPIConfig(
            api_id=self.node_id,
            name=_config_string(self.api_config, "name", self.node_id),
            description=_config_optional_string(self.api_config, "description"),
            url=raw_url,
            method=HTTPMethod(_config_string(self.api_config, "method", HTTPMethod.POST.value)),
            headers=_config_string_map_default(self.api_config, "headers"),
            timeout=_config_float(self.api_config, "timeout", 30.0),
            body_template=_config_string(self.api_config, "body_template", "{}"),
            state_mapping=_config_string_map_default(self.api_config, "state_mapping"),
        )

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """Вызывает внешний API с inputs как аргументами."""
        api_cfg = self._build_api_config()
        variables = state.variables

        client = ExternalAPIClient(timeout=api_cfg.timeout)
        result = require_json_object(
            await client.call(api_cfg, inputs, variables, state),
            "external_api.response",
        )

        if result.get("status") == "waiting_input" and result.get("interrupt"):
            interrupt_data = result["interrupt"]
            if not isinstance(interrupt_data, dict):
                raise ValueError(
                    f"ExternalAPINode: interrupt должен быть dict, получено {type(interrupt_data)}"
                )
            body = parse_interrupt_body_from_external_dict(
                require_json_object(interrupt_data, "external_api.interrupt"),
            )
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

    node_type: ClassVar[NodeType | None] = NodeType.MCP

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        super().__init__(node_id, config, container=container)
        cfg = self.config

        self.server_id: str | None = _config_optional_string(cfg, "server_id")
        self.tool_name: str | None = _config_optional_string(cfg, "tool_name")
        self.extra_headers: dict[str, str] = _config_string_map_default(cfg, "headers")
        self.state_mapping: dict[str, str] = _config_string_map_default(cfg, "state_mapping")

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """Вызывает MCP tool."""
        if not self.server_id:
            raise ValueError(f"MCPNode '{self.node_id}': server_id is required")
        if not self.tool_name:
            raise ValueError(f"MCPNode '{self.node_id}': tool_name is required")

        container = self.container
        if container is None:
            raise RuntimeError(f"MCP node '{self.node_id}' requires FlowContainer to load MCP server")

        server = await container.mcp_server_repository.get(self.server_id)
        if not server:
            raise ValueError(f"MCP server not found: {self.server_id}")

        if self.extra_headers:
            merged_headers = {**server.headers, **self.extra_headers}
            server.headers = merged_headers

        variables = state.variables

        client = MCPHttpClient(server, variables)
        result = await client.call_tool(self.tool_name, inputs)

        if result.is_error:
            raise ValueError(f"MCP tool error: {result.get_text()}")

        text_result = result.get_text()

        for _field, state_field in self.state_mapping.items():
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

    node_type: ClassVar[NodeType | None] = NodeType.CHANNEL

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        super().__init__(node_id, config, container=container)
        cfg = self.config

        channel_value = cfg.get("channel", "telegram")
        if not isinstance(channel_value, str):
            raise ValueError("channel: ожидается строка")
        self.channel: ChannelType = ChannelType(channel_value)
        self.action: str = _config_string(cfg, "action", "send_message")
        self.channel_config: JsonObject = _config_mapping_default(cfg, "channel_config")

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """Отправляет сообщение через channel handler."""
        container = self.container
        if container is None:
            raise RuntimeError(f"Channel node '{self.node_id}' requires FlowContainer to load channel registry")
        handler = container.channel_registry.get(self.channel)

        # Собираем все переменные (flow, компании, системные)
        all_variables = require_json_object(
            VariableResolver.resolve_all(local_vars=state.variables),
            "channel.all_variables",
        )

        # Merge channel_config с inputs
        config = {**self.channel_config}
        config = VarResolver.resolve_deep(config, all_variables)
        params = inputs
        variables = all_variables

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
                params=params,
                config=config,
                variables=variables,
            )

        setattr(state, "channel_result", result)
        setattr(state, "result", result)

        logger.info(
            f"[node:{self.node_id}] Channel {self.channel.value} "
            + f"action {self.action} completed"
        )

        return result


class HitlNode(BaseNode):
    """
    Нода передачи диалога оператору очереди (персистентная задача + interrupt).
    После complete в очереди: resume с тем же correlation — задача в БД completed,
    нода выставляет response и отдаёт управление следующим нодам по рёбрам.
    """

    node_type: ClassVar[NodeType | None] = NodeType.HITL_NODE

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        ctx = get_request_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError(
                f"hitl_node {self.node_id}: нужен Context с active_company"
            )
        company_id = ctx.active_company.company_id
        cid_resume = state.hitl_handoff_correlation_id
        if isinstance(cid_resume, str) and cid_resume.strip() and state.content:
            container = self.container
            if container is None:
                raise RuntimeError(f"HITL node '{self.node_id}' requires FlowContainer to load operator repository")
            repo = container.operator_repository
            existing_resume = await repo.get_task_by_correlation(
                company_id, cid_resume.strip()
            )
            if existing_resume is None:
                raise ValueError(
                    f"hitl_node {self.node_id}: resume с correlation_id={cid_resume!r}, "
                    + "задача оператора не найдена"
                )
            if existing_resume.status != OperatorTaskStatus.COMPLETED.value:
                raise ValueError(
                    f"hitl_node {self.node_id}: задача оператора ещё не завершена "
                    + f"(status={existing_resume.status!r})"
                )
            state.hitl_handoff_correlation_id = None
            answer = str(state.content).strip()
            state.response = answer
            return None

        slug_in = inputs.get("assignee_queue")
        slug_cfg = self.config.get("operator_queue_slug")
        qid_cfg = self.config.get("operator_queue_id")

        slug_effective: str
        if isinstance(slug_in, str) and slug_in.strip():
            slug_effective = slug_in.strip()
        elif isinstance(slug_cfg, str) and slug_cfg.strip():
            slug_effective = slug_cfg.strip()
        elif isinstance(qid_cfg, str) and qid_cfg.strip():
            container = self.container
            if container is None:
                raise RuntimeError(f"HITL node '{self.node_id}' requires FlowContainer to load operator queue")
            row = await container.operator_repository.get_queue_by_id(
                company_id, qid_cfg.strip()
            )
            if row is None:
                raise ValueError(
                    f"hitl_node {self.node_id}: очередь {qid_cfg!r} не найдена"
                )
            if not row.slug.strip():
                raise ValueError(
                    f"hitl_node {self.node_id}: у очереди {qid_cfg!r} не задан slug"
                )
            slug_effective = row.slug
        else:
            raise ValueError(
                f"hitl_node {self.node_id}: укажите operator_queue_slug, operator_queue_id "
                + "или input_mapping.assignee_queue"
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
                + "(user_facing_message / question / operator_user_message)"
            )

        raw_mode = (
            inputs.get("handoff_mode")
            or self.config.get("operator_handoff_mode")
            or "single_reply"
        )
        mode = HandoffMode(str(raw_mode).strip())

        container = self.container
        if container is None:
            raise RuntimeError(f"HITL node '{self.node_id}' requires FlowContainer to register handoff")
        svc = container.operator_handoff_service
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
    Рантайм не вызывает LLM и не мутирует state. LLM resource islands используются
    только при сборке LLM-конфига; sandbox code не получает resources как namespace.
    """

    name: ClassVar[str] = "resource"
    node_type: ClassVar[NodeType | None] = NodeType.RESOURCE

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> None:
        _ = state
        _ = inputs
        return None


def _infer_node_type_from_fields(node_config: JsonObject) -> None:
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


RUNTIME_NODE_CLASSES: Mapping[NodeType, type[BaseNode]] = {
    NodeType.LLM_NODE: LlmNode,
    NodeType.CODE: CodeNode,
    NodeType.FLOW: FlowNode,
    NodeType.REMOTE_FLOW: RemoteFlowNode,
    NodeType.EXTERNAL_API: ExternalAPINode,
    NodeType.MCP: MCPNode,
    NodeType.CHANNEL: ChannelNode,
    NodeType.HITL_NODE: HitlNode,
    NodeType.RESOURCE: ResourceNode,
}


async def create_node(
    node_id: str,
    node_config: JsonObject,
    *,
    container: FlowRuntimeContainer | None = None,
) -> BaseNode:
    """
    Создаёт ноду через NodeRegistry.

    Zero-Guess: неизвестный тип = исключение.
    """
    node_config = dict(node_config)
    legacy_llm = node_config.pop("llm_override", None)
    if isinstance(legacy_llm, dict) and legacy_llm:
        node_config["llm"] = legacy_llm
    t = node_config.get("type")
    if isinstance(t, str) and not t.strip():
        _ = node_config.pop("type", None)

    if not node_config.get("type"):
        code_value = node_config.get("code")
        if not (isinstance(code_value, str) and code_value.strip()):
            tool_id = node_config.get("tool_id")
            if tool_id:
                if container is None:
                    raise ValueError(
                        f"Node '{node_id}': tool_id без inline code требует FlowContainer"
                    )
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
        if not isinstance(node_type_value, str):
            raise ValueError(f"Node '{node_id}': type must be string, got {type(node_type_value).__name__}")
        node_type = NodeType(node_type_value)
    except ValueError:
        raise ValueError(f"Unknown node type: {node_type_value}")

    node_class = RUNTIME_NODE_CLASSES.get(node_type)
    if node_class is None:
        raise ValueError(f"Unknown node type: {node_type_value}")

    return node_class.from_config(node_id, node_config, container=container)
