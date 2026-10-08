"""
ExecutionState - типизированное состояние выполнения агента.

Замена dict state на строго типизированный класс.
Zero-Guess: все системные поля явно типизированы, нет магических __полей__.
"""

from __future__ import annotations

from copy import deepcopy
from typing import ClassVar, Literal, TypedDict, TypeVar, Unpack, cast, get_args, overload, override

from a2a.types import Message
from pydantic import (
    ConfigDict,
    Field,
    PrivateAttr,
    field_serializer,
    field_validator,
    model_validator,
)

from core.a2a.codec import messages_from_json_list, messages_to_json_list
from core.agent_plan.models import AgentPlan
from core.clients.llm.messages import LLMToolCall
from core.errors import FrozenStateFieldError
from core.files.file_ref import FileRef
from core.flow_ui.document import FlowUIBlock
from core.flow_ui.protocol import FlowUIAction, FlowUIEvent
from core.models import FlexibleBaseModel, StrictBaseModel
from core.reflection import ReflectionRecord
from core.state.interrupt import InterruptData
from core.state.mutation_policy import (
    FROZEN_STATE_SNAPSHOT_FIELDS,
    guard_setattr_if_user_code,
)
from core.state.trigger_runtime import TriggerRuntimeSnapshot
from core.types import JsonObject, JsonValue, require_json_object, require_json_value

ExecutionTaskState = Literal[
    "completed",
    "input-required",
    "canceled",
    "failed",
    "rejected",
    "auth-required",
    "handback",
    "unknown",
]
TERMINAL_TASK_STATES: frozenset[str] = frozenset(get_args(ExecutionTaskState))
FORBIDDEN_EXECUTION_STATE_FIELD_NAMES: frozenset[str] = frozenset(
    {"terminal_status", "terminal_error", "mock", "ui_document", "ui_values"}
)
ChildWorkflowStatus = Literal["running", "suspended", "completed", "failed"]


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
    hitl_streamed_closing_text: str | None
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
    handoff_parent_session_id: str | None
    handoff_depth: int
    handback_return_variables: JsonObject
    reasoning_history: list[JsonObject]
    reflection_history: list[ReflectionRecord]
    pending_reasoning: JsonObject | None
    agent_plan: AgentPlan | None
    breakpoints: dict[str, bool]
    breakpoint_hit: str | None
    breakpoint_state: JsonObject | None
    scheduled_tasks: list[JsonObject]
    join_arrived_preds: dict[str, list[str]]
    flow_deadline_monotonic: float | None
    flow_timeout_effective_seconds: int | None
    prompt_history: list[PromptHistoryItem]
    ui_action: FlowUIAction | None
    ui_slots: dict[str, list[FlowUIBlock]]
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
    child_execution_branch_id: str | None = Field(
        default=None,
        description="Durable execution branch id child workflow для resume FlowNode",
    )


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


class ChildWorkflowLink(StrictBaseModel):
    """Durable связь родительской ноды с отдельной child workflow-сессией."""

    node_id: str = Field(..., min_length=1)
    child_session_id: str = Field(..., min_length=3)
    child_flow_id: str = Field(..., min_length=1)
    child_flow_branch_id: str = Field(..., min_length=1)
    child_execution_branch_id: str = Field(..., min_length=1)
    parent_session_id: str = Field(..., min_length=3)
    parent_execution_branch_id: str = Field(..., min_length=1)
    parent_node_schedule_sequence: int = Field(..., ge=1)
    status: ChildWorkflowStatus
    handoff: bool = Field(default=False, description="Handoff или обычный child workflow")


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

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="allow",
        validate_assignment=False,
        use_enum_values=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
    )

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
    def validate_messages(cls, v: JsonValue | list[Message]) -> list[Message]:
        """Конвертирует словари в protobuf Message."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"messages: expected list, got {type(v)}")
        return messages_from_json_list(v)

    @field_serializer("messages", when_used="always")
    def serialize_messages(self, v: list[Message]) -> list[JsonObject]:
        return messages_to_json_list(v)

    @field_validator("interrupt_path", mode="before")
    @classmethod
    def validate_interrupt_path(
        cls, v: JsonValue | list[InterruptPathItem]
    ) -> list[InterruptPathItem]:
        """Конвертирует словари в объекты InterruptPathItem."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"interrupt_path: expected list, got {type(v)}")
        result: list[InterruptPathItem] = []
        for i, item in enumerate(v):
            if isinstance(item, InterruptPathItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(InterruptPathItem.model_validate(item))
            else:
                raise ValueError(
                    f"Unexpected item type #{i} in interrupt_path: {type(item)}. "
                    + 'Expected InterruptPathItem or dict.'
                )
        return result


ExecutionStateValue = (
    JsonValue
    | ExecutionTaskState
    | list[Message]
    | list[FileRef]
    | list[InterruptPathItem]
    | list[ExecutionExceptionRecord]
    | list[ReflectionRecord]
    | list[PromptHistoryItem]
    | dict[str, TriggerRuntimeSnapshot]
    | dict[str, NestedStateData]
    | dict[str, ChildWorkflowLink]
    | dict[str, bool]
    | dict[str, list[str]]
    | dict[str, list[FlowUIBlock]]
    | dict[str, int]
    | InterruptData
    | AgentPlan
    | FlowUIAction
    | LLMToolCall
)

_GetDefault = TypeVar("_GetDefault", bound=ExecutionStateValue)


def _trigger_field_dict[V](raw: dict[str, V]) -> dict[str, object]:
    copied: dict[str, object] = {}
    for key, value in raw.items():
        copied[key] = value
    return copied


class ExecutionState(FlexibleBaseModel):
    """
    Типизированное состояние выполнения агента.

    Замена dict state с магическими __полями__.
    Все системные поля явно типизированы и доступны через свойства.

    Zero-Guess принципы:
    - FlexibleBaseModel (extra='allow') - для runtime данных
    - Явные типы для системных полей
    - Нет магии, все через свойства

    Примеры:
        >>> state = ExecutionState.create(
        ...     task_id="task-123",
        ...     context_id="ctx-456",
        ...     user_id="user-789",
        ...     content="Hello"
        ... )
        >>> state.task_id  # Типизированный доступ
        'task-123'
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="allow",
        validate_assignment=False,
        use_enum_values=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
    )

    # ========================================================================
    # Системные поля - обязательные
    # ========================================================================

    task_id: str = Field(..., description="ID задачи A2A")
    context_id: str = Field(..., description="ID контекста A2A")
    user_id: str = Field(..., description="ID актора выполнения (сотрудник-агент или инициатор)")
    initiator_user_id: str | None = Field(
        default=None,
        description=(
            "Кто инициировал запуск: человек/собеседник. Для flow-сотрудника отличается от "
            "user_id (актор). Используется для уведомлений, эскалаций и prompt-переменных собеседника."
        ),
    )
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
    _pending_ui_events: list[FlowUIEvent] = PrivateAttr(default_factory=list)

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

    def queue_ui_events(self, events: list[FlowUIEvent]) -> None:
        """Render/navigate события ждут ближайшей точки публикации runtime."""
        self._pending_ui_events.extend(events)

    def pending_ui_events(self) -> list[FlowUIEvent]:
        """Копия очереди ui-событий, ещё не опубликованных runtime."""
        return list(self._pending_ui_events)

    def drain_ui_events(self) -> list[FlowUIEvent]:
        drained = list(self._pending_ui_events)
        self._pending_ui_events.clear()
        return drained

    def runtime_copy(self) -> ExecutionState:
        copied = ExecutionState.model_validate(self.model_dump(exclude_none=False))
        copied.attach_durable_node_context(
            execution_branch_id=self.durable_execution_branch_id,
            node_schedule_sequence=self.durable_node_schedule_sequence,
            superstep_sequence=self.durable_superstep_sequence,
        )
        copied.attach_durable_edge_context(
            execution_branch_id=self.durable_edge_execution_branch_id,
            edge_evaluation_sequence=self.durable_edge_evaluation_sequence,
        )
        copied.set_structured_output_result(self.structured_output_result)
        copied.queue_ui_events(list(self._pending_ui_events))
        return copied

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
    def reject_forbidden_system_field_names(cls, value: JsonValue) -> JsonValue:
        if not isinstance(value, dict):
            return value
        raw = value
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
                + "Session ID must contain ':' to extract flow_id."
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
    def validate_messages(cls, v: JsonValue | list[Message]) -> list[Message]:
        """Конвертирует словари в protobuf Message."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"messages: expected list, got {type(v)}")
        return messages_from_json_list(v)

    @field_serializer("messages", when_used="always")
    def serialize_messages(self, v: list[Message]) -> list[JsonObject]:
        return messages_to_json_list(v)

    @field_validator("execution_exceptions", mode="before")
    @classmethod
    def validate_execution_exceptions(
        cls, v: JsonValue | list[ExecutionExceptionRecord]
    ) -> list[ExecutionExceptionRecord]:
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"execution_exceptions: expected list, got {type(v)}")
        result: list[ExecutionExceptionRecord] = []
        for idx, item in enumerate(v):
            if isinstance(item, ExecutionExceptionRecord):
                result.append(item)
            elif isinstance(item, dict):
                result.append(ExecutionExceptionRecord.model_validate(item))
            else:
                raise ValueError(
                    f"execution_exceptions[{idx}]: expected ExecutionExceptionRecord or dict, "
                    + f"got {type(item)}"
                )
        return result

    @field_validator("triggers", mode="before")
    @classmethod
    def validate_triggers(
        cls, v: JsonValue | dict[str, TriggerRuntimeSnapshot]
    ) -> dict[str, TriggerRuntimeSnapshot]:
        if v is None or v == {}:
            return {}
        if not isinstance(v, dict):
            msg = f"triggers must be a dict, got {type(v).__name__}"
            raise TypeError(msg)
        out: dict[str, TriggerRuntimeSnapshot] = {}
        for key, item in v.items():
            if key == "":
                msg = "triggers keys must be non-empty strings"
                raise TypeError(msg)
            if isinstance(item, TriggerRuntimeSnapshot):
                out[key] = item
            elif isinstance(item, dict):
                raw_item = item
                payload = raw_item.get("payload")
                if not isinstance(payload, dict):
                    msg = f"triggers['{key}'] must include 'payload' as a dict"
                    raise ValueError(msg)
                ctx = raw_item.get("context", {})
                if not isinstance(ctx, dict):
                    msg = f"triggers['{key}'].context must be a dict"
                    raise TypeError(msg)
                out[key] = TriggerRuntimeSnapshot(
                    payload=_trigger_field_dict(payload),
                    context=_trigger_field_dict(ctx),
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
    # Прерывание (ask_user)
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
    hitl_streamed_closing_text: str | None = Field(
        default=None,
        description=(
            "Текст closing operator reply, уже отправленный в Redis как operator_reply. "
            "Если final_response совпадает — emit_complete не дублирует его в UI completed."
        ),
    )

    @field_validator("interrupt", mode="before")
    @classmethod
    def validate_interrupt(cls, v: JsonValue | InterruptData) -> InterruptData | None:
        """Конвертирует dict в InterruptData (для inline кода)."""
        if v is None:
            return None
        if isinstance(v, InterruptData):
            return v
        if isinstance(v, dict):
            return InterruptData.model_validate(v)
        raise ValueError(
            f"Unexpected interrupt type: {type(v)}. "
            + 'Expected InterruptData or dict.'
        )

    @override
    def __setattr__(self, name: str, value: ExecutionStateValue) -> None:
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
        assigned = value
        if name == "interrupt" and assigned is not None and type(assigned) is not InterruptData:
            value = InterruptData.model_validate(require_json_object(assigned, "interrupt"))
        if name == "child_workflows" and assigned is not None:
            if isinstance(assigned, dict) and all(
                isinstance(item, ChildWorkflowLink) for item in assigned.values()
            ):
                value = assigned
            else:
                value = type(self).validate_child_workflows(
                    require_json_object(assigned, "child_workflows")
                )
        if name == "prompt_history" and assigned is not None:
            if isinstance(assigned, list) and all(
                isinstance(item, PromptHistoryItem) for item in assigned
            ):
                value = assigned
            else:
                value = ExecutionState.normalize_prompt_history(
                    require_json_value(assigned, "prompt_history")
                )
        super().__setattr__(name, value)

    @field_validator("interrupt_path", mode="before")
    @classmethod
    def validate_interrupt_path(
        cls, v: JsonValue | list[InterruptPathItem]
    ) -> list[InterruptPathItem]:
        """Конвертирует словари в объекты InterruptPathItem."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"interrupt_path: expected list, got {type(v)}")
        result: list[InterruptPathItem] = []
        for i, item in enumerate(v):
            if isinstance(item, InterruptPathItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(InterruptPathItem.model_validate(item))
            else:
                raise ValueError(
                    f"Unexpected item type #{i} in interrupt_path: {type(item)}. "
                    + 'Expected InterruptPathItem or dict.'
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
    handoff_parent_session_id: str | None = Field(
        default=None,
        description="ID родительской сессии у дочернего flow при handoff — чтобы знать куда handback'ить",
    )
    handoff_depth: int = Field(
        default=0,
        ge=0,
        description="Глубина цепочки handoff (для отладки и лимитов)",
    )
    handoff_trace_id: str | None = Field(
        default=None,
        min_length=1,
        description="OTEL trace_id цепочки handoff parent↔child для observability",
    )
    handback_return_variables: JsonObject = Field(
        default_factory=dict,
        description="Переменные, явно возвращаемые родителю через handback_to_parent",
    )
    @field_validator("child_workflows", mode="before")
    @classmethod
    def validate_child_workflows(
        cls, v: JsonValue | dict[str, ChildWorkflowLink]
    ) -> dict[str, ChildWorkflowLink]:
        if v is None or v == {}:
            return {}
        if not isinstance(v, dict):
            raise ValueError(f"child_workflows: expected dict, got {type(v)}")
        result: dict[str, ChildWorkflowLink] = {}
        for key, item in v.items():
            if key == "":
                raise ValueError("child_workflows keys must be non-empty strings")
            if isinstance(item, ChildWorkflowLink):
                result[key] = item
            elif isinstance(item, dict):
                result[key] = ChildWorkflowLink.model_validate(item)
            else:
                raise ValueError(
                    f"child_workflows[{key!r}]: expected ChildWorkflowLink or dict, "
                    + f"got {type(item)}"
                )
        return result

    # ========================================================================
    # Reasoning (рассуждение tool)
    # ========================================================================

    reasoning_history: list[JsonObject] = Field(
        default_factory=list,
        description="История рассуждений агента"
    )
    reflection_history: list[ReflectionRecord] = Field(
        default_factory=list,
        description="Typed reflection/test-time compute gate history",
    )
    pending_reasoning: JsonObject | None = Field(
        default=None,
        description="Текущее pending рассуждение"
    )
    agent_plan: AgentPlan | None = Field(
        default=None,
        description="Активный AgentPlan (flat checklist); перетирается agent_plan_write",
    )

    @field_validator("agent_plan", mode="before")
    @classmethod
    def _validate_agent_plan(cls, value: JsonValue | AgentPlan) -> AgentPlan | None:
        if value is None:
            return None
        if isinstance(value, AgentPlan):
            return value
        if isinstance(value, dict):
            return AgentPlan.model_validate(value)
        raise ValueError(
            f"agent_plan: expected AgentPlan | dict | None, got {type(value)}"
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
    ui_action: FlowUIAction | None = Field(
        default=None,
        description="Событие текущего хода от интерактивного блока интерфейса",
    )
    ui_slots: dict[str, list[FlowUIBlock]] = Field(
        default_factory=dict,
        description="Блоки, отрендеренные агентом, по целям рендера (slot_id)",
    )
    llm_context_memory_cursor: dict[str, int] = Field(
        default_factory=dict,
        description="Закрытый offset сообщений для episodic memory context layer",
    )

    @staticmethod
    def normalize_prompt_history(v: JsonValue | list[PromptHistoryItem]) -> list[PromptHistoryItem]:
        """Единая нормализация: dict/list dict -> List[PromptHistoryItem]."""
        if v is None or v == []:
            return []
        if not isinstance(v, list):
            raise ValueError(f"prompt_history: expected list, got {type(v)}")
        result: list[PromptHistoryItem] = []
        for item in v:
            if isinstance(item, PromptHistoryItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(PromptHistoryItem.model_validate(item))
            else:
                raise ValueError(
                    f"Expected PromptHistoryItem or dict, got {type(item)}"
                )
        return result

    @field_validator("prompt_history", mode="before")
    @classmethod
    def validate_prompt_history(cls, v: JsonValue | list[PromptHistoryItem]) -> list[PromptHistoryItem]:
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

        Аргументы:
            task_id: ID задачи
            context_id: ID контекста
            user_id: ID пользователя
            session_id: ID сессии в формате flow_id:context_id
            content: Входное сообщение
            branch_id: ID skill
            **kwargs: Дополнительные поля

        Возвращает:
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

    def __getitem__(self, key: str) -> ExecutionStateValue:
        """Поддержка доступа через квадратные скобки."""
        if key in type(self).model_fields:
            return cast(ExecutionStateValue, self.__dict__[key])
        if self.__pydantic_extra__ and key in self.__pydantic_extra__:
            return cast(ExecutionStateValue, self.__pydantic_extra__[key])
        raise KeyError(key)

    def __setitem__(self, key: str, value: ExecutionStateValue) -> None:
        """Поддержка присваивания через квадратные скобки."""
        self.__setattr__(key, value)

    @overload
    def get(self, key: Literal["messages"], default: list[Message]) -> list[Message]: ...

    @overload
    def get(self, key: Literal["files"], default: list[JsonObject]) -> list[JsonObject]: ...

    @overload
    def get(self, key: Literal["tool_results"], default: JsonObject) -> JsonObject: ...

    @overload
    def get(self, key: str, default: _GetDefault) -> ExecutionStateValue | _GetDefault: ...

    @overload
    def get(self, key: str) -> ExecutionStateValue | None: ...

    def get(self, key: str, default: ExecutionStateValue | None = None) -> ExecutionStateValue | None:
        """Поддержка метода get как у dict."""
        try:
            return self[key]
        except KeyError:
            return default


def snapshot_frozen_fields(state: ExecutionState) -> dict[str, ExecutionStateValue]:
    """Глубокий снимок frozen-полей до исполнения user/eval-кода.

    Живёт в слое модели (не в mutation_policy): снимок хранит
    ``ExecutionStateValue`` — политика состояния типом не оперирует.
    """
    out: dict[str, ExecutionStateValue] = {}
    for key in FROZEN_STATE_SNAPSHOT_FIELDS:
        out[key] = deepcopy(state[key])
    return out


def assert_frozen_fields_unchanged(
    state: ExecutionState,
    snapshot: dict[str, ExecutionStateValue],
) -> None:
    """Проверяет, что user/eval-код не поменял frozen-поля in-place."""
    for key, old_val in snapshot.items():
        if old_val != state[key]:
            raise FrozenStateFieldError(
                field=key,
                reason="in_place_mutation",
            )


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
    "ReflectionRecord",
    "snapshot_frozen_fields",
    "assert_frozen_fields_unchanged",
]
