"""Pydantic-схемы записей, попадающих в полу-произвольные поля ExecutionState.

Эти поля исторически объявлены как ``JsonObject`` / ``list[JsonObject]``
ради совместимости с persistence (Redis snapshot и `workflow_events`
replay в durable runtime), а форма данных закреплена контрактом writers'ов
(`runtime/flow.py`, `runtime/runners`, `tools/scheduling.py`,
`state/interrupt_manager.py`). Модели ниже фиксируют этот контракт явно —
их можно использовать в писателях/читателях через ``model_validate`` /
``model_dump(mode='json')``, чтобы не разъезжалась форма между местами
записи/чтения.

Поля ExecutionState, документируемые этими моделями:

* ``node_history: dict[str, NodeHistoryEntry]`` — статистика и calls по
  каждой ноде.
* ``tool_results: dict[str, ToolResult]`` — последние результаты тулов.
* ``reasoning_history: list[ReasoningEntry]`` — история reasoning блоков.
* ``pending_reasoning: ReasoningEntry | None`` — текущий открытый reasoning.
* ``breakpoint_state: BreakpointState | None`` — состояние активного
  breakpoint (если есть).
* ``scheduled_tasks: list[ScheduledTaskRef]`` — projection локального
  scheduler ledger в state (см. ``apps/flows/tools/scheduling.py``).

Принцип Zero-Guess: каждое поле — Pydantic с явным описанием.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.types import JsonObject, JsonValue


class NodeCallRecord(BaseModel):
    """Один вызов ноды в рамках суперстепа.

    Заполняется ``Flow._execute_node`` (`apps/flows/src/runtime/flow.py`):
    ``response`` — payload ноды, ``validation`` — отчёт валидации,
    ``timestamp`` — ISO начала вызова.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    response: JsonValue = Field(default=None, description="Ответ ноды")
    validation: JsonObject | None = Field(default=None, description="Отчёт валидации")
    timestamp: str | None = Field(default=None, description="ISO время вызова")


class NodeHistoryEntry(BaseModel):
    """Запись в ``ExecutionState.node_history`` под ключом ``node_id``."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    type: str = Field(description="Тип ноды (NodeType.value)")
    calls: list[NodeCallRecord] = Field(
        default_factory=list,
        description="Хронология вызовов ноды в этом Flow.run",
    )


class ToolResult(BaseModel):
    """Последний результат вызова инструмента в ``ExecutionState.tool_results``.

    Ключ внешнего dict — ``tool_call_id`` (или составной ``node_id:tool_name``).
    ``content`` — нормализованный текст ответа (для LLM), ``raw`` —
    исходный объект ответа (если зафиксирован), ``error`` — текст ошибки,
    если вызов завершился исключением.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    tool_name: str = Field(description="Имя инструмента")
    content: str | None = Field(default=None, description="Текстовый ответ инструмента")
    raw: JsonValue = Field(default=None, description="Сырое тело ответа (если сохраняется)")
    error: str | None = Field(default=None, description="Текст ошибки, если вызов упал")


class ReasoningEntry(BaseModel):
    """Запись reasoning блока для совместимости с провайдерскими reasoning API.

    Заполняется ``LLMRunner`` при стриминге reasoning chunks; см.
    ``ExecutionState.reasoning_history``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    node_id: str | None = Field(default=None)
    content: str = Field(default="")
    finished: bool = Field(default=False)


class BreakpointState(BaseModel):
    """Снимок состояния runtime при сработавшем breakpoint."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    breakpoint_id: str = Field(description="ID сработавшего breakpoint")
    snapshot: JsonObject = Field(
        default_factory=dict,
        description="Подмножество ExecutionState, зафиксированное при срабатывании",
    )


class ScheduledTaskRef(BaseModel):
    """Локальная projection scheduled task в state.

    Минимальный контракт — поля, на которые опираются ``apps/flows/tools/scheduling.py``
    и читатели в ``apps/flows/src/services/schedule_service.py``. ``content`` —
    строка для напоминания (``content_type='reminder'``) или имя tool
    (``content_type='tool_call'``); ``tool_args`` обязательны только при
    ``content_type='tool_call'``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    schedule_task_id: str = Field(description="ID платформенного scheduler task")
    content: str = Field(description="Reminder text или tool name")
    content_type: Literal["reminder", "tool_call"] = Field(
        default="reminder",
        description="reminder — текст-напоминание; tool_call — вызов tool",
    )
    cron: str | None = Field(default=None, description="Cron-выражение для периодической задачи")
    interval_seconds: int | None = Field(default=None, ge=1)
    run_at: str | None = Field(default=None, description="ISO одноразовый запуск")
    tool_args: JsonObject | None = Field(default=None, description="Аргументы tool_call")
    description: str | None = Field(default=None)


__all__ = [
    "BreakpointState",
    "NodeCallRecord",
    "NodeHistoryEntry",
    "ReasoningEntry",
    "ScheduledTaskRef",
    "ToolResult",
]
