"""
ExecutionState - типизированное состояние выполнения агента.

Замена dict state на строго типизированный класс.
Zero-Guess: все системные поля явно типизированы, нет магических __полей__.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypedDict, TypeVar, Unpack, cast, get_args, overload, override

from a2a.types import Message
from pydantic import (
    Field,
    PrivateAttr,
    field_serializer,
    field_validator,
    model_validator,
)

from core.clients.llm.messages import LLMToolCall
from core.files.file_ref import FileRef
from core.models import FlexibleBaseModel, StrictBaseModel
from core.state.interrupt import InterruptData
from core.state.mutation_policy import guard_setattr_if_user_code
from core.state.trigger_runtime import TriggerRuntimeSnapshot
from core.types import JsonObject, JsonValue, require_json_object

ExecutionTaskState = Literal[
    "completed",
    "input-required",
    "canceled",
    "failed",
    "rejected",
    "auth-required",
    "unknown",
]
TERMINAL_TASK_STATES: frozenset[str] = frozenset(get_args(ExecutionTaskState))
FORBIDDEN_EXECUTION_STATE_FIELD_NAMES: frozenset[str] = frozenset(
    {"terminal_status", "terminal_error", "mock"}
)
ChildWorkflowStatus = Literal["running", "suspended", "completed", "failed"]
_GetDefault = TypeVar("_GetDefault")


class ExecutionStateCreateKwargs(TypedDict, total=False):
    flow_config_version: str | None
    terminal_task_state: ExecutionTaskState | None
    terminal_task_error: str | None
    current_nodes: list[str]
    response: str | None
    result: JsonValue
    validation: JsonObject | None
    messages: list[Message]
    user_groups: list[str]
    variables: JsonObject
    triggers: dict[str, TriggerRuntimeSnapshot]
    files: list[FileRef]
    interrupt: InterruptData | None
    interrupt_path: list[InterruptPathItem]
    hitl_handoff_correlation_id: str | None
    # Pydantic-схемы значений документированы в
    # `core/state/execution_state_records.py`:
    # node_history — NodeHistoryEntry, tool_results — ToolResult,
    # reasoning_history/pending_reasoning — ReasoningEntry,
    # breakpoint_state — BreakpointState, scheduled_tasks — ScheduledTaskRef.
    node_history: dict[str, JsonObject]
    tool_results: JsonObject
    execution_exceptions: list[ExecutionExceptionRecord]
    nested_states: dict[str, NestedStateData]
    child_workflows: dict[str, ChildWorkflowLink]
    reasoning_history: list[JsonObject]
    pending_reasoning: JsonObject | None
    breakpoints: dict[str, bool]
    breakpoint_hit: str | None
    breakpoint_state: JsonObject | None
    scheduled_tasks: list[JsonObject]
    join_arrived_preds: dict[str, list[str]]
    flow_deadline_monotonic: float | None
    flow_timeout_effective_seconds: int | None
    prompt_history: list[PromptHistoryItem]
    ui_events_pending: list[PendingUIEvent]
    llm_context_memory_cursor: dict[str, int]


class InterruptPathItem(FlexibleBaseModel):
    """Элемент пути прерывания."""

    node_type: str = Field(..., description="Тип: tool, llm_node, flow")
    node_id: str = Field(..., description="ID ноды/tool")
    tool_call: LLMToolCall | None = Field(default=None, description="Данные tool_call")
    child_session_id: str | None = Field(
        default=None,
        description="Durable session_id child workflow для resume FlowNode",
    )
    child_flow_id: str | None = Field(default=None, description="ID child flow")
    child_flow_branch_id: str | None = Field(default=None, description="Branch child flow")


class NodeCallInfo(FlexibleBaseModel):
    """Информация о вызове ноды"""

    response: JsonValue = Field(default=None, description="Ответ ноды")
    validation: JsonObject | None = Field(default=None, description="Данные валидации")
    timestamp: str | None = Field(default=None, description="Время вызова")


class ExecutionExceptionRecord(FlexibleBaseModel):
    """Запись об исключении, обработанном как ответ (режим exception_as_response)."""

    node_id: str = Field(..., description="Нода, в контексте которой произошло исключение")
    source: Literal["node_run", "tool"] = Field(
        ...,
        description="node_run — падение _run_impl; tool — ошибка вызова инструмента в llm_node",
    )
    exception_type: str = Field(..., description="Имя класса исключения (type(exc).__name__)")
    message: str = Field(..., description="Текст исключения")
    tool_name: str | None = Field(default=None, description="Имя tool при source=tool")
    tool_call_id: str | None = Field(default=None, description="ID tool_call при source=tool")


class PendingUIEvent(StrictBaseModel):
    """UI event, queued in ExecutionState until the runtime emits it to the A2A stream."""

    event_id: str = Field(..., description="ID события")
    event_type: str = Field(..., description="Тип события")
    payload: JsonObject = Field(..., description="Payload события")
    version: str = Field(..., description="Версия события")
    timestamp: str = Field(..., description="Время создания ISO")
    source: str = Field(..., description="Источник события")
    correlation_id: str | None = Field(default=None, description="Correlation id")


class ChildWorkflowLink(StrictBaseModel):
    """Durable связь родительской ноды с отдельной child workflow-сессией."""

    node_id: str = Field(..., min_length=1)
    child_session_id: str = Field(..., min_length=3)
    child_flow_id: str = Field(..., min_length=1)
    child_flow_branch_id: str = Field(..., min_length=1)
    parent_session_id: str = Field(..., min_length=3)
    parent_execution_branch_id: str = Field(..., min_length=1)
    parent_node_schedule_sequence: int = Field(..., ge=1)
    status: ChildWorkflowStatus


class PromptHistoryItem(FlexibleBaseModel):
    """Запись истории изменений системного промпта."""

    prompt_hash: str = Field(..., description="MD5 хеш промпта для сравнения")
    prompt: str = Field(..., description="Рендеренный промпт")
    template: str = Field(..., description="Исходный шаблон")
    variables_used: JsonObject = Field(default_factory=dict, description="Использованные переменные")
    node_id: str = Field(..., description="ID ноды которая сгенерировала промпт")
    timestamp: str = Field(..., description="Время создания ISO")


class NestedStateData(FlexibleBaseModel):
    """Данные вложенного состояния для субагентов."""

    messages: list[Message] = Field(default_factory=list, description="История сообщений субагента")
    interrupt_path: list[InterruptPathItem] = Field(
        default_factory=list,
        description="Путь прерывания внутри субагента"
    )
    nested_states: dict[str, NestedStateData] = Field(
        default_factory=dict,
        description="Вложенные состояния суб-субагентов"
    )

    @field_validator("messages", mode="before")
    @classmethod
    def validate_messages(cls, v: object) -> list[Message]:
        """Конвертирует словари в объекты Message."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"messages: ожидается list, получен {type(v)}")
        result: list[Message] = []
        for item in cast(list[object], v):
            if isinstance(item, Message):
                result.append(item)
            elif isinstance(item, dict):
                result.append(Message.model_validate(item))
            else:
                raise ValueError(
                    f"Ожидается Message или dict, получен {type(item)}"
                )
        return result

    @field_validator("interrupt_path", mode="before")
    @classmethod
    def validate_interrupt_path(cls, v: object) -> list[InterruptPathItem]:
        """Конвертирует словари в объекты InterruptPathItem."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"interrupt_path: ожидается list, получен {type(v)}")
        result: list[InterruptPathItem] = []
        for i, item in enumerate(cast(list[object], v)):
            if isinstance(item, InterruptPathItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(InterruptPathItem.model_validate(item))
            else:
                raise ValueError(
                    f"Неожиданный тип элемента #{i} в interrupt_path: {type(item)}. "
                    + "Ожидается InterruptPathItem или dict."
                )
        return result


class ExecutionState(FlexibleBaseModel):
    """
    Типизированное состояние выполнения агента.

    Замена dict state с магическими __полями__.
    Все системные поля явно типизированы и доступны через свойства.

    Zero-Guess принципы:
    - FlexibleBaseModel (extra='allow') - для runtime данных
    - Явные типы для системных полей
    - Нет магии, все через свойства

    Examples:
        >>> state = ExecutionState.create(
        ...     task_id="task-123",
        ...     context_id="ctx-456",
        ...     user_id="user-789",
        ...     content="Hello"
        ... )
        >>> state.task_id  # Типизированный доступ
        'task-123'
    """

    # ========================================================================
    # Системные поля - обязательные
    # ========================================================================

    task_id: str = Field(..., description="ID задачи A2A")
    context_id: str = Field(..., description="ID контекста A2A")
    user_id: str = Field(..., description="ID пользователя")
    session_id: str = Field(..., description="ID сессии в формате flow_id:context_id")

    # ========================================================================
    # Снимок конфигурации flow в БД (полный граф не хранится в state)
    # ========================================================================

    flow_config_version: str | None = Field(
        default=None,
        description="Версия FlowConfig в flows_versions; None = при выполнении брать последнюю из flows",
    )
    terminal_task_state: ExecutionTaskState | None = Field(
        default=None,
        description="Финальный A2A TaskState, сохранённый в БД только на terminal boundary.",
    )
    terminal_task_error: str | None = Field(
        default=None,
        description="Текст ошибки для terminal_task_state='failed'/'rejected'/'unknown'.",
    )

    # ========================================================================
    # Системные поля - опциональные
    # ========================================================================

    current_nodes: list[str] = Field(default_factory=list, description="Текущие ноды для выполнения")
    branch_id: str = Field(default="default", description="ID branch")

    _durable_execution_branch_id: str | None = PrivateAttr(default=None)
    _durable_node_schedule_sequence: int | None = PrivateAttr(default=None)
    _durable_superstep_sequence: int | None = PrivateAttr(default=None)
    _durable_edge_execution_branch_id: str | None = PrivateAttr(default=None)
    _durable_edge_evaluation_sequence: int | None = PrivateAttr(default=None)
    _structured_output_result: JsonValue = PrivateAttr(default=None)

    @property
    def durable_execution_branch_id(self) -> str | None:
        return self._durable_execution_branch_id

    @property
    def durable_node_schedule_sequence(self) -> int | None:
        return self._durable_node_schedule_sequence

    @property
    def durable_superstep_sequence(self) -> int | None:
        return self._durable_superstep_sequence

    @property
    def durable_edge_execution_branch_id(self) -> str | None:
        return self._durable_edge_execution_branch_id

    @property
    def durable_edge_evaluation_sequence(self) -> int | None:
        return self._durable_edge_evaluation_sequence

    @property
    def structured_output_result(self) -> JsonValue:
        return self._structured_output_result

    def set_structured_output_result(self, value: JsonValue) -> None:
        self._structured_output_result = value

    def clear_structured_output_result(self) -> None:
        self._structured_output_result = None

    def attach_durable_node_context(
        self,
        *,
        execution_branch_id: str | None,
        node_schedule_sequence: int | None,
        superstep_sequence: int | None,
    ) -> None:
        if execution_branch_id is not None:
            self._durable_execution_branch_id = execution_branch_id
        if node_schedule_sequence is not None:
            self._durable_node_schedule_sequence = node_schedule_sequence
        if superstep_sequence is not None:
            self._durable_superstep_sequence = superstep_sequence

    def attach_durable_edge_context(
        self,
        *,
        execution_branch_id: str | None,
        edge_evaluation_sequence: int | None,
    ) -> None:
        if execution_branch_id is not None:
            self._durable_edge_execution_branch_id = execution_branch_id
        if edge_evaluation_sequence is not None:
            self._durable_edge_evaluation_sequence = edge_evaluation_sequence

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_system_field_names(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        raw = cast(Mapping[str, object], value)
        forbidden_field_names = sorted(
            FORBIDDEN_EXECUTION_STATE_FIELD_NAMES.intersection(raw.keys())
        )
        if forbidden_field_names:
            names = ", ".join(forbidden_field_names)
            raise ValueError(
                f"ExecutionState system field names are forbidden: {names}. "
                + "Use terminal_task_state and terminal_task_error."
            )
        return dict(raw)

    @field_validator("session_id")
    @classmethod
    def validate_session_id_format(cls, v: str) -> str:
        """Валидирует что session_id в формате flow_id:context_id."""
        if not v:
            raise ValueError("session_id is required")
        if ":" not in v:
            raise ValueError(
                f"session_id must be in format 'flow_id:context_id', got: '{v}'. "
                + "Session ID должен содержать ':' для извлечения flow_id."
            )
        flow_id, context_id = v.split(":", 1)
        if not flow_id:
            raise ValueError(f"flow_id part of session_id is empty: '{v}'")
        if not context_id:
            raise ValueError(f"context_id part of session_id is empty: '{v}'")
        return v

    @property
    def session_flow_id(self) -> str:
        """flow_id из session_id (формат flow_id:context_id)."""
        return self.session_id.split(":", 1)[0]


    # ========================================================================
    # Данные пользователя
    # ========================================================================

    content: str | None = Field(default=None, description="Входное сообщение")
    response: str | None = Field(default=None, description="Ответ агента")
    result: JsonValue = Field(
        default=None,
        description="Произвольный результат ноды или tool (CodeNode, inline execute)",
    )
    validation: JsonObject | None = Field(
        default=None,
        description="Данные валидации ноды (условия рёбер вида validation.valid == true)",
    )
    messages: list[Message] = Field(default_factory=list, description="История сообщений")
    user_groups: list[str] = Field(default_factory=list, description="Группы пользователя")

    @field_validator("messages", mode="before")
    @classmethod
    def validate_messages(cls, v: object) -> list[Message]:
        """Конвертирует словари в объекты Message."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"messages: ожидается list, получен {type(v)}")
        result: list[Message] = []
        for item in cast(list[object], v):
            if isinstance(item, Message):
                result.append(item)
            elif isinstance(item, dict):
                result.append(Message.model_validate(item))
            else:
                raise ValueError(
                    f"Ожидается Message или dict, получен {type(item)}"
                )
        return result

    @field_validator("execution_exceptions", mode="before")
    @classmethod
    def validate_execution_exceptions(cls, v: object) -> list[ExecutionExceptionRecord]:
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"execution_exceptions: ожидается list, получен {type(v)}")
        result: list[ExecutionExceptionRecord] = []
        for idx, item in enumerate(cast(list[object], v)):
            if isinstance(item, ExecutionExceptionRecord):
                result.append(item)
            elif isinstance(item, dict):
                result.append(ExecutionExceptionRecord.model_validate(item))
            else:
                raise ValueError(
                    f"execution_exceptions[{idx}]: ожидается ExecutionExceptionRecord или dict, "
                    + f"получен {type(item)}"
                )
        return result

    @field_validator("triggers", mode="before")
    @classmethod
    def validate_triggers(
        cls, v: object
    ) -> dict[str, TriggerRuntimeSnapshot]:
        if v is None or v == {}:
            return {}
        if not isinstance(v, dict):
            msg = f"triggers must be a dict, got {type(v).__name__}"
            raise TypeError(msg)
        out: dict[str, TriggerRuntimeSnapshot] = {}
        for key, item in cast(Mapping[object, object], v).items():
            if not isinstance(key, str):
                msg = f"triggers keys must be str, got {type(key).__name__}"
                raise TypeError(msg)
            if isinstance(item, TriggerRuntimeSnapshot):
                out[key] = item
            elif isinstance(item, dict):
                raw_item = cast(Mapping[str, object], item)
                payload = raw_item.get("payload")
                if not isinstance(payload, dict):
                    msg = f"triggers['{key}'] must include 'payload' as a dict"
                    raise ValueError(msg)
                ctx = raw_item.get("context", {})
                if not isinstance(ctx, dict):
                    msg = f"triggers['{key}'].context must be a dict"
                    raise TypeError(msg)
                out[key] = TriggerRuntimeSnapshot(
                    payload=dict(cast(Mapping[str, object], payload)),
                    context=dict(cast(Mapping[str, object], ctx)),
                )
            else:
                msg = f"triggers['{key}'] must be TriggerRuntimeSnapshot or dict, got {type(item).__name__}"
                raise TypeError(msg)
        return out

    # ========================================================================
    # Переменные и данные
    # ========================================================================

    variables: JsonObject = Field(default_factory=dict, description="Резолвнутые переменные")
    triggers: dict[str, TriggerRuntimeSnapshot] = Field(
        default_factory=dict,
        description="Снимок по trigger_id: { payload, context } — не смешивать с variables",
    )
    files: list[FileRef] = Field(default_factory=list, description="Прикреплённые файлы")

    # ========================================================================
    # Interrupt (ask_user)
    # ========================================================================

    interrupt: InterruptData | None = Field(default=None, description="Данные прерывания")
    interrupt_path: list[InterruptPathItem] = Field(
        default_factory=list,
        description="Путь к месту прерывания"
    )
    hitl_handoff_correlation_id: str | None = Field(
        default=None,
        description=(
            "При resume после operator handoff: correlation_id задачи до сброса interrupt, "
            "чтобы hitl_node один раз завершилась и граф пошёл дальше по рёбрам"
        ),
    )

    @field_validator("interrupt", mode="before")
    @classmethod
    def validate_interrupt(cls, v: object) -> InterruptData | None:
        """Конвертирует dict в InterruptData (для inline кода)."""
        if v is None:
            return None
        if isinstance(v, InterruptData):
            return v
        if isinstance(v, dict):
            return InterruptData.model_validate(cast(object, v))
        raise ValueError(
            f"Неожиданный тип interrupt: {type(v)}. "
            + "Ожидается InterruptData или dict."
        )

    @override
    def __setattr__(self, name: str, value: object) -> None:
        """
        Перехватывает прямое присваивание атрибутов.
        Нормализует dict -> типизированные модели при присваивании.
        """
        if name.startswith("__pydantic"):
            super().__setattr__(name, value)
            return
        if name in FORBIDDEN_EXECUTION_STATE_FIELD_NAMES:
            raise ValueError(
                f"ExecutionState system field name is forbidden: {name}. "
                + "Use terminal_task_state or terminal_task_error."
            )
        guard_setattr_if_user_code(name)
        if name == "interrupt" and value is not None and isinstance(value, dict):
            value = InterruptData.model_validate(cast(object, value))
        if name == "child_workflows" and value is not None:
            value = type(self).validate_child_workflows(value)
        if name == "prompt_history" and value is not None:
            value = ExecutionState.normalize_prompt_history(value)
        super().__setattr__(name, value)

    @field_validator("interrupt_path", mode="before")
    @classmethod
    def validate_interrupt_path(cls, v: object) -> list[InterruptPathItem]:
        """Конвертирует словари в объекты InterruptPathItem."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"interrupt_path: ожидается list, получен {type(v)}")
        result: list[InterruptPathItem] = []
        for i, item in enumerate(cast(list[object], v)):
            if isinstance(item, InterruptPathItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(InterruptPathItem.model_validate(item))
            else:
                raise ValueError(
                    f"Неожиданный тип элемента #{i} в interrupt_path: {type(item)}. "
                    + "Ожидается InterruptPathItem или dict."
                )
        return result

    # ========================================================================
    # История выполнения
    # ========================================================================

    node_history: dict[str, JsonObject] = Field(
        default_factory=dict,
        description=(
            "История вызовов нод за последний проход Flow.run: {node_id: {type, calls: [...]}}. "
            "Сбрасывается в начале каждого Flow.run; лимит повторных заходов в code-ноду считается только в этом проходе."
        ),
    )
    tool_results: JsonObject = Field(
        default_factory=dict,
        description="Результаты выполнения tools {tool_id: result}"
    )
    execution_exceptions: list[ExecutionExceptionRecord] = Field(
        default_factory=list,
        description="Реестр исключений, обработанных как ответ (exception_as_response на ноде)",
    )
    nested_states: dict[str, NestedStateData] = Field(
        default_factory=dict,
        description="Состояния вложенных субагентов"
    )
    child_workflows: dict[str, ChildWorkflowLink] = Field(
        default_factory=dict,
        description=(
            "Durable child workflow links по node_id; хранит session_id child flow "
            "для resume без snapshot-копии child state в родителе."
        ),
    )
    @field_validator("child_workflows", mode="before")
    @classmethod
    def validate_child_workflows(cls, v: object) -> dict[str, ChildWorkflowLink]:
        if v is None or v == {}:
            return {}
        if not isinstance(v, dict):
            raise ValueError(f"child_workflows: ожидается dict, получен {type(v)}")
        result: dict[str, ChildWorkflowLink] = {}
        for key, item in cast(Mapping[object, object], v).items():
            if not isinstance(key, str) or not key:
                raise ValueError("child_workflows keys must be non-empty strings")
            if isinstance(item, ChildWorkflowLink):
                result[key] = item
            elif isinstance(item, dict):
                result[key] = ChildWorkflowLink.model_validate(cast(object, item))
            else:
                raise ValueError(
                    f"child_workflows[{key!r}]: ожидается ChildWorkflowLink или dict, "
                    + f"получен {type(item)}"
                )
        return result

    # ========================================================================
    # Reasoning (tool reason)
    # ========================================================================

    reasoning_history: list[JsonObject] = Field(
        default_factory=list,
        description="История рассуждений агента"
    )
    pending_reasoning: JsonObject | None = Field(
        default=None,
        description="Текущее pending рассуждение"
    )

    # ========================================================================
    # Точки перелома (отладка)
    # ========================================================================

    breakpoints: dict[str, bool] = Field(
        default_factory=dict,
        description="Активные breakpoints для нод (node_id -> enabled)"
    )
    breakpoint_hit: str | None = Field(
        default=None,
        description="ID ноды, на которой сработал breakpoint"
    )
    breakpoint_state: JsonObject | None = Field(
        default=None,
        description="Projection snapshot на момент срабатывания breakpoint"
    )

    # ========================================================================
    # Запланированные задачи
    # ========================================================================

    scheduled_tasks: list[JsonObject] = Field(
        default_factory=list,
        description="Scheduled tasks созданные в текущей сессии"
    )

    join_arrived_preds: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "AND-join (incoming_policy=all): target_node_id -> предки, уже пришедшие в текущем цикле ожидания"
        ),
    )

    flow_deadline_monotonic: float | None = Field(
        default=None,
        description=(
            "Дедлайн одного вызова run flow: time.monotonic() <= flow_deadline_monotonic; "
            "None — wall-clock лимит не задан для этой сессии"
        ),
    )
    flow_timeout_effective_seconds: int | None = Field(
        default=None,
        description="Секунд wall-clock, заданных на этот run (для ошибок и отладки)",
    )

    # ========================================================================
    # История системных промптов
    # ========================================================================

    prompt_history: list[PromptHistoryItem] = Field(
        default_factory=list,
        description="История изменений системного промпта"
    )
    ui_events_pending: list[PendingUIEvent] = Field(
        default_factory=list,
        description="UI events, ожидающие публикации в A2A stream",
    )
    llm_context_memory_cursor: dict[str, int] = Field(
        default_factory=dict,
        description="Закрытый offset сообщений для episodic memory context layer",
    )

    @staticmethod
    def normalize_prompt_history(v: object) -> list[PromptHistoryItem]:
        """Единая нормализация: dict/list dict -> List[PromptHistoryItem]."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"prompt_history: ожидается list, получен {type(v)}")
        result: list[PromptHistoryItem] = []
        for item in cast(list[object], v):
            if isinstance(item, PromptHistoryItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(PromptHistoryItem.model_validate(item))
            else:
                raise ValueError(
                    f"Ожидается PromptHistoryItem или dict, получен {type(item)}"
                )
        return result

    @field_validator("prompt_history", mode="before")
    @classmethod
    def validate_prompt_history(cls, v: object) -> list[PromptHistoryItem]:
        return cls.normalize_prompt_history(v)

    @field_serializer("prompt_history", when_used="always")
    def serialize_prompt_history(self, v: list[PromptHistoryItem]) -> list[JsonObject]:
        return [
            require_json_object(item.model_dump(mode="json"), "prompt_history[]")
            for item in v
        ]

    @property
    def current_system_prompt(self) -> str | None:
        """Текущий системный промпт (последний из истории)."""
        if not self.prompt_history:
            return None
        return self.prompt_history[-1].prompt

    @classmethod
    def create(
        cls,
        task_id: str,
        context_id: str,
        user_id: str,
        session_id: str,
        content: str | None = None,
        branch_id: str = "default",
        **kwargs: Unpack[ExecutionStateCreateKwargs],
    ) -> ExecutionState:
        """
        Создаёт новое состояние выполнения.

        Args:
            task_id: ID задачи
            context_id: ID контекста
            user_id: ID пользователя
            session_id: ID сессии в формате flow_id:context_id
            content: Входное сообщение
            branch_id: ID skill
            **kwargs: Дополнительные поля

        Returns:
            ExecutionState
        """
        return cls(
            task_id=task_id,
            context_id=context_id,
            user_id=user_id,
            session_id=session_id,
            content=content,
            branch_id=branch_id,
            **kwargs
        )

    def __contains__(self, key: str) -> bool:
        """Поддержка оператора 'in' для доступа к полям как к dict."""
        if key in type(self).model_fields:
            return True
        if self.__pydantic_extra__:
            return key in self.__pydantic_extra__
        return False

    def __getitem__(self, key: str) -> object:
        """Поддержка доступа через квадратные скобки."""
        if key in type(self).model_fields:
            return cast(object, self.__dict__[key])
        if self.__pydantic_extra__ and key in self.__pydantic_extra__:
            return cast(object, self.__pydantic_extra__[key])
        raise KeyError(key)

    def __setitem__(self, key: str, value: object) -> None:
        """Поддержка присваивания через квадратные скобки."""
        self.__setattr__(key, value)

    @overload
    def get(self, key: Literal["messages"], default: list[Message]) -> list[Message]: ...

    @overload
    def get(self, key: Literal["files"], default: list[JsonObject]) -> list[JsonObject]: ...

    @overload
    def get(self, key: Literal["tool_results"], default: JsonObject) -> JsonObject: ...

    @overload
    def get(self, key: str, default: _GetDefault) -> object | _GetDefault: ...

    @overload
    def get(self, key: str) -> object | None: ...

    def get(self, key: str, default: object | None = None) -> object | None:
        """Поддержка метода get как у dict."""
        try:
            return self[key]
        except KeyError:
            return default


# Короткий алиас для удобства
State = ExecutionState

__all__ = [
    "ExecutionState",
    "ExecutionTaskState",
    "State",
    "TERMINAL_TASK_STATES",
    "InterruptData",
    "InterruptPathItem",
    "NodeCallInfo",
    "NestedStateData",
    "ChildWorkflowLink",
    "ChildWorkflowStatus",
    "PromptHistoryItem",
    "ExecutionExceptionRecord",
]
