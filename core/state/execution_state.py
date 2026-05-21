"""
ExecutionState - типизированное состояние выполнения агента.

Замена dict state на строго типизированный класс.
Zero-Guess: все системные поля явно типизированы, нет магических __полей__.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from a2a.types import Message
from pydantic import Field, field_serializer, field_validator

from core.models import FlexibleBaseModel
from core.state.interrupt import InterruptData
from core.state.mutation_policy import guard_setattr_if_user_code
from core.state.trigger_runtime import TriggerRuntimeSnapshot


class InterruptPathItem(FlexibleBaseModel):
    """Элемент пути прерывания"""

    type: str = Field(..., description="Тип: tool, llm_node, flow")
    id: str = Field(..., description="ID ноды/tool")
    tool_call: Optional[Dict[str, Any]] = Field(default=None, description="Данные tool_call")


class NodeCallInfo(FlexibleBaseModel):
    """Информация о вызове ноды"""

    response: Any = Field(default=None, description="Ответ ноды")
    validation: Optional[Dict[str, Any]] = Field(default=None, description="Данные валидации")
    timestamp: Optional[str] = Field(default=None, description="Время вызова")


class ExecutionExceptionRecord(FlexibleBaseModel):
    """Запись об исключении, обработанном как ответ (режим exception_as_response)."""

    node_id: str = Field(..., description="Нода, в контексте которой произошло исключение")
    source: Literal["node_run", "tool"] = Field(
        ...,
        description="node_run — падение _run_impl; tool — ошибка вызова инструмента в llm_node",
    )
    exception_type: str = Field(..., description="Имя класса исключения (type(exc).__name__)")
    message: str = Field(..., description="Текст исключения")
    tool_name: Optional[str] = Field(default=None, description="Имя tool при source=tool")
    tool_call_id: Optional[str] = Field(default=None, description="ID tool_call при source=tool")


class PromptHistoryItem(FlexibleBaseModel):
    """Запись истории изменений системного промпта."""

    prompt_hash: str = Field(..., description="MD5 хеш промпта для сравнения")
    prompt: str = Field(..., description="Рендеренный промпт")
    template: str = Field(..., description="Исходный шаблон")
    variables_used: Dict[str, Any] = Field(default_factory=dict, description="Использованные переменные")
    node_id: str = Field(..., description="ID ноды которая сгенерировала промпт")
    timestamp: str = Field(..., description="Время создания ISO")


class NestedStateData(FlexibleBaseModel):
    """Данные вложенного состояния для субагентов."""

    messages: List[Message] = Field(default_factory=list, description="История сообщений субагента")
    interrupt_path: List[InterruptPathItem] = Field(
        default_factory=list,
        description="Путь прерывания внутри субагента"
    )
    nested_states: Dict[str, NestedStateData] = Field(
        default_factory=dict,
        description="Вложенные состояния суб-субагентов"
    )

    @field_validator("messages", mode="before")
    @classmethod
    def validate_messages(cls, v: Any) -> List[Message]:
        """Конвертирует словари в объекты Message."""
        if not v:
            return []
        result = []
        for i, item in enumerate(v):
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
    def validate_interrupt_path(cls, v: Any) -> List[InterruptPathItem]:
        """Конвертирует словари в объекты InterruptPathItem."""
        if not v:
            return []
        result = []
        for i, item in enumerate(v):
            if isinstance(item, InterruptPathItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(InterruptPathItem.model_validate(item))
            else:
                raise ValueError(
                    f"Неожиданный тип элемента #{i} в interrupt_path: {type(item)}. "
                    f"Ожидается InterruptPathItem или dict."
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

    flow_config_version: Optional[str] = Field(
        default=None,
        description="Версия FlowConfig в flows_versions; None = при выполнении брать последнюю из flows",
    )
    terminal_status: Optional[
        Literal[
            "completed",
            "input-required",
            "canceled",
            "failed",
            "rejected",
            "auth-required",
            "unknown",
        ]
    ] = Field(
        default=None,
        description="Финальный A2A status, сохранённый в БД только на terminal boundary.",
    )
    terminal_error: Optional[str] = Field(
        default=None,
        description="Текст ошибки для terminal_status='failed'/'rejected'/'unknown'.",
    )

    # ========================================================================
    # Системные поля - опциональные
    # ========================================================================

    current_nodes: List[str] = Field(default_factory=list, description="Текущие ноды для выполнения")
    branch_id: str = Field(default="default", description="ID skill")

    @field_validator("session_id")
    @classmethod
    def validate_session_id_format(cls, v: str) -> str:
        """Валидирует что session_id в формате flow_id:context_id."""
        if not v:
            raise ValueError("session_id is required")
        if ":" not in v:
            raise ValueError(
                f"session_id must be in format 'flow_id:context_id', got: '{v}'. "
                "Session ID должен содержать ':' для извлечения flow_id."
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

    content: Optional[str] = Field(default=None, description="Входное сообщение")
    response: Optional[str] = Field(default=None, description="Ответ агента")
    result: Optional[Any] = Field(
        default=None,
        description="Произвольный результат ноды или tool (CodeNode, inline execute)",
    )
    validation: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Данные валидации ноды (условия рёбер вида validation.valid == true)",
    )
    messages: List[Message] = Field(default_factory=list, description="История сообщений")
    user_groups: List[str] = Field(default_factory=list, description="Группы пользователя")

    @field_validator("messages", mode="before")
    @classmethod
    def validate_messages(cls, v: Any) -> List[Message]:
        """Конвертирует словари в объекты Message."""
        if not v:
            return []
        result = []
        for i, item in enumerate(v):
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
    def validate_execution_exceptions(cls, v: Any) -> List[ExecutionExceptionRecord]:
        if not v:
            return []
        result: List[ExecutionExceptionRecord] = []
        for idx, item in enumerate(v):
            if isinstance(item, ExecutionExceptionRecord):
                result.append(item)
            elif isinstance(item, dict):
                result.append(ExecutionExceptionRecord.model_validate(item))
            else:
                raise ValueError(
                    f"execution_exceptions[{idx}]: ожидается ExecutionExceptionRecord или dict, "
                    f"получен {type(item)}"
                )
        return result

    @field_validator("triggers", mode="before")
    @classmethod
    def validate_triggers(
        cls, v: Any
    ) -> Dict[str, TriggerRuntimeSnapshot]:
        if v is None or v == {}:
            return {}
        if not isinstance(v, dict):
            msg = f"triggers must be a dict, got {type(v).__name__}"
            raise TypeError(msg)
        out: Dict[str, TriggerRuntimeSnapshot] = {}
        for k, item in v.items():
            if isinstance(item, TriggerRuntimeSnapshot):
                out[k] = item
            elif isinstance(item, dict):
                if "payload" not in item or not isinstance(item.get("payload"), dict):
                    msg = f"triggers['{k}'] must include 'payload' as a dict"
                    raise ValueError(msg)
                ctx = item.get("context", {})
                if not isinstance(ctx, dict):
                    msg = f"triggers['{k}'].context must be a dict"
                    raise TypeError(msg)
                out[k] = TriggerRuntimeSnapshot(
                    payload=item["payload"],
                    context=ctx,
                )
            else:
                msg = f"triggers['{k}'] must be TriggerRuntimeSnapshot or dict, got {type(item).__name__}"
                raise TypeError(msg)
        return out

    # ========================================================================
    # Переменные и данные
    # ========================================================================

    variables: Dict[str, Any] = Field(default_factory=dict, description="Резолвнутые переменные")
    triggers: Dict[str, TriggerRuntimeSnapshot] = Field(
        default_factory=dict,
        description="Снимок по trigger_id: { payload, context } — не смешивать с variables",
    )
    files: List[Dict[str, Any]] = Field(default_factory=list, description="Прикреплённые файлы")

    # ========================================================================
    # Interrupt (ask_user)
    # ========================================================================

    interrupt: Optional[InterruptData] = Field(default=None, description="Данные прерывания")
    interrupt_path: List[InterruptPathItem] = Field(
        default_factory=list,
        description="Путь к месту прерывания"
    )
    hitl_handoff_correlation_id: Optional[str] = Field(
        default=None,
        description=(
            "При resume после operator handoff: correlation_id задачи до сброса interrupt, "
            "чтобы hitl_node один раз завершилась и граф пошёл дальше по рёбрам"
        ),
    )

    @field_validator("interrupt", mode="before")
    @classmethod
    def validate_interrupt(cls, v: Any) -> Optional[InterruptData]:
        """Конвертирует dict в InterruptData (для inline кода)."""
        if v is None:
            return None
        if isinstance(v, InterruptData):
            return v
        if isinstance(v, dict):
            return InterruptData.model_validate(v)
        raise ValueError(
            f"Неожиданный тип interrupt: {type(v)}. "
            f"Ожидается InterruptData или dict."
        )

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Перехватывает прямое присваивание атрибутов.
        Нормализует dict -> типизированные модели при присваивании.
        """
        if name.startswith("__pydantic"):
            super().__setattr__(name, value)
            return
        guard_setattr_if_user_code(name)
        if name == "interrupt" and value is not None and isinstance(value, dict):
            value = InterruptData.model_validate(value)
        if name == "prompt_history" and value is not None:
            value = ExecutionState.normalize_prompt_history(value)
        super().__setattr__(name, value)

    @field_validator("interrupt_path", mode="before")
    @classmethod
    def validate_interrupt_path(cls, v: Any) -> List[InterruptPathItem]:
        """Конвертирует словари в объекты InterruptPathItem."""
        if not v:
            return []
        result = []
        for i, item in enumerate(v):
            if isinstance(item, InterruptPathItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(InterruptPathItem.model_validate(item))
            else:
                raise ValueError(
                    f"Неожиданный тип элемента #{i} в interrupt_path: {type(item)}. "
                    f"Ожидается InterruptPathItem или dict."
                )
        return result

    # ========================================================================
    # История выполнения
    # ========================================================================

    node_history: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "История вызовов нод за последний проход Flow.run: {node_id: {type, calls: [...]}}. "
            "Сбрасывается в начале каждого Flow.run; лимит повторных заходов в code-ноду считается только в этом проходе."
        ),
    )
    tool_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="Результаты выполнения tools {tool_id: result}"
    )
    execution_exceptions: List[ExecutionExceptionRecord] = Field(
        default_factory=list,
        description="Реестр исключений, обработанных как ответ (exception_as_response на ноде)",
    )
    nested_states: Dict[str, NestedStateData] = Field(
        default_factory=dict,
        description="Состояния вложенных субагентов"
    )
    mock: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Mock конфигурация для тестирования"
    )

    # ========================================================================
    # Reasoning (tool reason)
    # ========================================================================

    reasoning_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="История рассуждений агента"
    )
    pending_reasoning: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Текущее pending рассуждение"
    )

    # ========================================================================
    # Точки перелома (отладка)
    # ========================================================================

    breakpoints: Dict[str, bool] = Field(
        default_factory=dict,
        description="Активные breakpoints для нод (node_id -> enabled)"
    )
    breakpoint_hit: Optional[str] = Field(
        default=None,
        description="ID ноды, на которой сработал breakpoint"
    )
    breakpoint_state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Snapshot state на момент срабатывания breakpoint"
    )

    # ========================================================================
    # Запланированные задачи
    # ========================================================================

    scheduled_tasks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Scheduled tasks созданные в текущей сессии"
    )

    join_arrived_preds: Dict[str, List[str]] = Field(
        default_factory=dict,
        description=(
            "AND-join (incoming_policy=all): target_node_id -> предки, уже пришедшие в текущем цикле ожидания"
        ),
    )

    flow_deadline_monotonic: Optional[float] = Field(
        default=None,
        description=(
            "Дедлайн одного вызова run flow: time.monotonic() <= flow_deadline_monotonic; "
            "None — wall-clock лимит не задан для этой сессии"
        ),
    )
    flow_timeout_effective_seconds: Optional[int] = Field(
        default=None,
        description="Секунд wall-clock, заданных на этот run (для ошибок и отладки)",
    )

    # ========================================================================
    # История системных промптов
    # ========================================================================

    prompt_history: List[PromptHistoryItem] = Field(
        default_factory=list,
        description="История изменений системного промпта"
    )

    @staticmethod
    def normalize_prompt_history(v: Any) -> List[PromptHistoryItem]:
        """Единая нормализация: dict/list dict -> List[PromptHistoryItem]."""
        if not v:
            return []
        result = []
        for item in v:
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
    def validate_prompt_history(cls, v: Any) -> List[PromptHistoryItem]:
        return cls.normalize_prompt_history(v)

    @field_serializer("prompt_history", when_used="always")
    def serialize_prompt_history(self, v: List[PromptHistoryItem]) -> List[Any]:
        return [
            x.model_dump() if isinstance(x, PromptHistoryItem) else PromptHistoryItem.model_validate(x).model_dump()
            for x in v
        ]

    @property
    def current_system_prompt(self) -> Optional[str]:
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
        content: Optional[str] = None,
        branch_id: str = "default",
        **kwargs
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
        if hasattr(self, key):
            return True
        if hasattr(self, '__pydantic_extra__') and self.__pydantic_extra__:
            return key in self.__pydantic_extra__
        return False

    def __getitem__(self, key: str) -> Any:
        """Поддержка доступа через квадратные скобки."""
        if hasattr(self, key):
            return getattr(self, key)
        if hasattr(self, '__pydantic_extra__') and self.__pydantic_extra__ and key in self.__pydantic_extra__:
            return self.__pydantic_extra__[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Поддержка присваивания через квадратные скобки."""
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """Поддержка метода get как у dict."""
        try:
            return self[key]
        except KeyError:
            return default


# Короткий алиас для удобства
State = ExecutionState

__all__ = [
    "ExecutionState",
    "State",
    "InterruptData",
    "InterruptPathItem",
    "NodeCallInfo",
    "NestedStateData",
    "PromptHistoryItem",
    "ExecutionExceptionRecord",
]
