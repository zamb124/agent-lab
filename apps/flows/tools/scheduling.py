"""
Tools для управления scheduled tasks.

Позволяют агентам создавать и управлять отложенными задачами.
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.eval.platform_services import get_schedule_service
from apps.flows.src.tools import tool
from core.scheduler.models import ContentType
from core.state import ExecutionState


def _extract_ids_from_state(state: ExecutionState) -> Tuple[str, str, str]:
    """
    Извлекает flow_id, session_id, user_id из state.

    session_id ОБЯЗАТЕЛЕН и ВСЕГДА в формате 'flow_id:context_id'.
    Валидация формата происходит в ExecutionState.
    """
    session_id = state.session_id
    if not session_id:
        raise ValueError("session_id is required in state for scheduling tools")

    if ":" not in session_id:
        raise ValueError(
            f"session_id must be in format 'flow_id:context_id', got: '{session_id}'"
        )

    flow_id = session_id.split(":")[0]
    user_id = state.user_id or ""

    return flow_id, session_id, user_id


class _ScheduledTaskContentArgs(BaseModel):
    """Общие поля для создания задачи с полезной нагрузкой message или tool_call."""

    model_config = ConfigDict(extra="forbid")

    content_type: Literal["message", "tool_call"] = Field(
        ...,
        description='Тип: "message" — текст в сессию чата; "tool_call" — вызов тула по имени.',
    )
    content: str = Field(
        ...,
        min_length=1,
        description="При message — текст сообщения; при tool_call — имя тула (tool_id).",
    )
    tool_args: Optional[Dict[str, Any]] = Field(
        None,
        description="Аргументы для tool_call (объект JSON); для message обычно не передаётся.",
    )
    description: Optional[str] = Field(
        None,
        description="Краткое описание задачи для списка и логов планировщика.",
    )


class ScheduleCronArgs(_ScheduledTaskContentArgs):
    cron: str = Field(
        ...,
        min_length=1,
        description="Cron из 5 полей, например '0 10 * * *' (ежедневно 10:00) или '*/5 * * * *' (каждые 5 минут).",
    )


class ScheduleIntervalArgs(_ScheduledTaskContentArgs):
    interval_minutes: int = Field(
        ...,
        ge=1,
        description="Период повтора в минутах.",
    )


class ScheduleOneTimeArgs(_ScheduledTaskContentArgs):
    run_at: str = Field(
        ...,
        min_length=1,
        description="Момент запуска в ISO 8601, например 2026-01-15T10:00:00.",
    )


class CancelScheduledTaskArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: str = Field(
        ...,
        min_length=1,
        description="UUID или полный id задачи, как в ответе при создании или в list_scheduled_tasks.",
    )


class ListScheduledTasksArgs(BaseModel):
    """Список задач берётся из state.session_id; отдельных аргументов нет."""

    model_config = ConfigDict(extra="forbid")


@tool(
    name="schedule_cron_task",
    description="Создает периодическую задачу по cron расписанию. Примеры cron: '0 10 * * *' (каждый день в 10:00), '*/5 * * * *' (каждые 5 минут), '0 9 * * 1' (каждый понедельник в 9:00)",
    tags=["scheduling"],
    args_schema=ScheduleCronArgs,
)
async def schedule_cron_task(
    cron: str,
    content_type: str,
    content: str,
    tool_args: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
    *,
    state: ExecutionState,
) -> str:
    """
    Создает периодическую задачу по cron.

    Args:
        cron: Cron выражение
        content_type: "message" или "tool_call"
        content: Текст сообщения или имя tool
        tool_args: Аргументы для tool_call
        description: Описание задачи
        state: Состояние агента
    """
    service = get_schedule_service()

    ct = ContentType(content_type)
    flow_id, session_id, user_id = _extract_ids_from_state(state)

    task = await service.schedule_cron_task(
        flow_id=flow_id,
        session_id=session_id,
        user_id=user_id,
        cron=cron,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )

    state.scheduled_tasks.append(task.model_dump())

    return f"Периодическая задача создана (ID: {task.id}). Расписание: {cron}"


@tool(
    name="schedule_interval_task",
    description="Создает периодическую задачу с интервалом в минутах",
    tags=["scheduling"],
    args_schema=ScheduleIntervalArgs,
)
async def schedule_interval_task(
    interval_minutes: int,
    content_type: str,
    content: str,
    tool_args: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
    *,
    state: ExecutionState,
) -> str:
    """
    Создает периодическую задачу с интервалом.

    Args:
        interval_minutes: Интервал в минутах
        content_type: "message" или "tool_call"
        content: Текст сообщения или имя tool
        tool_args: Аргументы для tool_call
        description: Описание задачи
        state: Состояние агента
    """
    service = get_schedule_service()

    ct = ContentType(content_type)
    flow_id, session_id, user_id = _extract_ids_from_state(state)

    task = await service.schedule_interval_task(
        flow_id=flow_id,
        session_id=session_id,
        user_id=user_id,
        interval_minutes=interval_minutes,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )

    state.scheduled_tasks.append(task.model_dump())

    return f"Периодическая задача создана (ID: {task.id}). Интервал: каждые {interval_minutes} минут"


@tool(
    name="schedule_one_time_task",
    description="Создает одноразовую задачу на конкретное время. Формат времени: ISO 8601 (например '2025-01-15T10:00:00')",
    tags=["scheduling"],
    args_schema=ScheduleOneTimeArgs,
)
async def schedule_one_time_task(
    run_at: str,
    content_type: str,
    content: str,
    tool_args: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
    *,
    state: ExecutionState,
) -> str:
    """
    Создает одноразовую задачу.

    Args:
        run_at: Время запуска в формате ISO 8601
        content_type: "message" или "tool_call"
        content: Текст сообщения или имя tool
        tool_args: Аргументы для tool_call
        description: Описание задачи
        state: Состояние агента
    """
    service = get_schedule_service()

    ct = ContentType(content_type)
    run_at_dt = datetime.fromisoformat(run_at)
    flow_id, session_id, user_id = _extract_ids_from_state(state)

    task = await service.schedule_one_time_task(
        flow_id=flow_id,
        session_id=session_id,
        user_id=user_id,
        run_at=run_at_dt,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )

    state.scheduled_tasks.append(task.model_dump())

    return f"Одноразовая задача создана (ID: {task.id}). Запуск: {run_at}"


@tool(
    name="list_scheduled_tasks",
    description="Показывает список запланированных задач текущей сессии",
    tags=["scheduling"],
    args_schema=ListScheduledTasksArgs,
)
async def list_scheduled_tasks(
    *,
    state: ExecutionState,
) -> str:
    """
    Получает список scheduled tasks.

    Args:
        state: Состояние агента
    """
    service = get_schedule_service()

    _, session_id, _ = _extract_ids_from_state(state)

    tasks = await service.list_tasks(session_id=session_id)

    if not tasks:
        return "Нет запланированных задач"

    lines = ["Запланированные задачи:"]
    for task in tasks:
        schedule_info = ""
        schedule_type = task.schedule_type if isinstance(task.schedule_type, str) else task.schedule_type.value
        content_type = task.content_type if isinstance(task.content_type, str) else task.content_type.value
        status = task.status if isinstance(task.status, str) else task.status.value

        if schedule_type == "cron":
            schedule_info = f"cron: {task.cron}"
        elif schedule_type == "interval":
            schedule_info = f"каждые {task.interval_minutes} мин"
        elif schedule_type == "one_time":
            schedule_info = f"запуск: {task.run_at}"

        content_info = f"{content_type}: {task.content}"
        desc = f" - {task.description}" if task.description else ""

        lines.append(f"- [{task.id[:8]}] {schedule_info}, {content_info}, статус: {status}{desc}")

    return "\n".join(lines)


@tool(
    name="cancel_scheduled_task",
    description="Отменяет запланированную задачу по её ID",
    tags=["scheduling"],
    args_schema=CancelScheduledTaskArgs,
)
async def cancel_scheduled_task(
    task_id: str,
    *,
    state: ExecutionState,
) -> str:
    """
    Отменяет задачу.

    Args:
        task_id: ID задачи
        state: Состояние агента
    """
    service = get_schedule_service()

    success = await service.cancel_task(task_id)

    if success:
        state.scheduled_tasks = [t for t in state.scheduled_tasks if t.get("id") != task_id]
        return f"Задача {task_id} отменена"
    else:
        return f"Не удалось отменить задачу {task_id}. Возможно она уже выполнена или не существует."
