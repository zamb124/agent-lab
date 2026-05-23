"""
Поля ExecutionState - общие для всех языков.

Соответствие модели: core.state.execution_state.ExecutionState.
readonly: True — поле выставляет рантайм/граф; во inline-коде обычно только читают.
"""

from typing import Any

STATE_FIELDS: list[dict[str, Any]] = [
    {
        "name": "task_id",
        "type": "str",
        "description": "Идентификатор задачи A2A.",
        "readonly": True,
    },
    {
        "name": "context_id",
        "type": "str",
        "description": "Идентификатор контекста A2A.",
        "readonly": True,
    },
    {
        "name": "user_id",
        "type": "str",
        "description": "Идентификатор пользователя.",
        "readonly": True,
    },
    {
        "name": "session_id",
        "type": "str",
        "description": "Сессия в формате `flow_id:context_id` (см. свойство `session_flow_id` для flow_id).",
        "readonly": True,
    },
    {
        "name": "flow_config_version",
        "type": "Optional[str]",
        "description": "Версия FlowConfig в `flows_versions`; None — при выполнении берётся последняя.",
        "readonly": True,
    },
    {
        "name": "terminal_task_state",
        "type": "Optional[ExecutionTaskState]",
        "description": "Сохранённый terminal A2A TaskState (`completed`, `input-required`, `failed` и др.).",
        "readonly": True,
    },
    {
        "name": "terminal_task_error",
        "type": "Optional[str]",
        "description": "Текст ошибки для terminal_task_state `failed`, `rejected`, `unknown`.",
        "readonly": True,
    },
    {
        "name": "branch_id",
        "type": "str",
        "description": "Активный branch (по умолчанию `default`).",
        "readonly": True,
    },
    {
        "name": "current_nodes",
        "type": "List[str]",
        "description": "Идентификаторы нод текущего шага графа.",
        "readonly": True,
    },
    {
        "name": "content",
        "type": "Optional[str]",
        "description": "Текст последнего сообщения пользователя.",
        "readonly": False,
    },
    {
        "name": "response",
        "type": "Optional[str]",
        "description": "Ответ агента пользователю.",
        "readonly": False,
    },
    {
        "name": "result",
        "type": "Any",
        "description": "Результат ноды или inline tool (произвольный сериализуемый объект).",
        "readonly": False,
    },
    {
        "name": "validation",
        "type": "Optional[Dict[str, Any]]",
        "description": "Данные для условий рёбер (например `validation.valid`).",
        "readonly": False,
    },
    {
        "name": "messages",
        "type": "List[Message]",
        "description": "История диалога (A2A Message).",
        "readonly": False,
    },
    {
        "name": "user_groups",
        "type": "List[str]",
        "description": "Группы пользователя в компании.",
        "readonly": True,
    },
    {
        "name": "variables",
        "type": "Dict[str, Any]",
        "description": "Резолвнутые переменные flow; в глобалах дублируется снимок `variables` (только чтение).",
        "readonly": True,
    },
    {
        "name": "triggers",
        "type": "Dict[str, Any]",
        "description": "Данные триггеров `{trigger_id: payload}`.",
        "readonly": False,
    },
    {
        "name": "files",
        "type": "List[dict]",
        "description": "Вложения: `original_name`, `url`, `content_type`, `file_size`, `file_id` и др.",
        "readonly": True,
    },
    {
        "name": "interrupt",
        "type": "Optional[InterruptData]",
        "description": "Данные прерывания (ask_user, OAuth, operator handoff).",
        "readonly": False,
    },
    {
        "name": "interrupt_path",
        "type": "List[InterruptPathItem]",
        "description": "Путь к месту прерывания в графе.",
        "readonly": True,
    },
    {
        "name": "hitl_handoff_correlation_id",
        "type": "Optional[str]",
        "description": "При resume после operator handoff: correlation_id до сброса interrupt.",
        "readonly": True,
    },
    {
        "name": "node_history",
        "type": "Dict[str, Dict[str, Any]]",
        "description": (
            "История вызовов нод за последний проход Flow.run: `{node_id: {type, calls: [...]}}`; "
            "сбрасывается в начале каждого Flow.run."
        ),
        "readonly": True,
    },
    {
        "name": "tool_results",
        "type": "Dict[str, Any]",
        "description": "Результаты tools `{tool_id: result}`.",
        "readonly": True,
    },
    {
        "name": "nested_states",
        "type": "Dict[str, NestedStateData]",
        "description": "Состояния вложенных субагентов.",
        "readonly": False,
    },
    {
        "name": "mock",
        "type": "Optional[Dict[str, Any]]",
        "description": "Mock-конфигурация для тестов.",
        "readonly": True,
    },
    {
        "name": "reasoning_history",
        "type": "List[Dict[str, Any]]",
        "description": "История рассуждений (tool reason и аналоги).",
        "readonly": False,
    },
    {
        "name": "pending_reasoning",
        "type": "Optional[Dict[str, Any]]",
        "description": "Текущее незавершённое рассуждение.",
        "readonly": False,
    },
    {
        "name": "breakpoints",
        "type": "Dict[str, bool]",
        "description": "Отладка: breakpoints `node_id -> enabled`.",
        "readonly": False,
    },
    {
        "name": "breakpoint_hit",
        "type": "Optional[str]",
        "description": "ID ноды, на которой сработал breakpoint.",
        "readonly": False,
    },
    {
        "name": "breakpoint_state",
        "type": "Optional[Dict[str, Any]]",
        "description": "Снимок state при breakpoint.",
        "readonly": True,
    },
    {
        "name": "scheduled_tasks",
        "type": "List[Dict[str, Any]]",
        "description": "Запланированные задачи текущей сессии.",
        "readonly": True,
    },
    {
        "name": "join_arrived_preds",
        "type": "Dict[str, List[str]]",
        "description": "AND-join: для `target_node_id` — предки, уже пришедшие в цикле ожидания.",
        "readonly": True,
    },
    {
        "name": "prompt_history",
        "type": "List[PromptHistoryItem]",
        "description": "История изменений системного промпта; последний элемент — текущий (см. `current_system_prompt`).",
        "readonly": False,
    },
]
