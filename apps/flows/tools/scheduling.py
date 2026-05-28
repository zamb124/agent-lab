"""
Tools для управления scheduled tasks.

Позволяют агентам создавать и управлять отложенными задачами.
"""

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.services.platform_facades import get_schedule_service
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.scheduling_ids import extract_ids_from_state
from core.scheduler.models import ContentType
from core.state import ExecutionState
from core.types import JsonObject


def _extract_ids_from_state(state: ExecutionState) -> tuple[str, str, str]:
    return extract_ids_from_state(state)


class _ScheduledTaskContentArgs(BaseModel):
    """Общие поля для создания задачи с полезной нагрузкой message или tool_call."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    content_type: Literal["message", "tool_call"] = Field(
        ...,
        description='Тип: "message" — текст в сессию чата; "tool_call" — вызов тула по имени.',
    )
    content: str = Field(
        ...,
        min_length=1,
        description="При message — текст сообщения; при tool_call — имя тула (tool_id).",
    )
    tool_args: JsonObject | None = Field(
        None,
        description="Аргументы для tool_call (объект JSON); для message обычно не передаётся.",
    )
    description: str | None = Field(
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
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schedule_task_id: str = Field(
        ...,
        min_length=1,
        description="schedule_task_id задачи, как в ответе при создании или в list_scheduled_tasks.",
    )


class ListScheduledTasksArgs(BaseModel):
    """Список задач берётся из state.session_id; отдельных аргументов нет."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


@tool(
    name="schedule_cron_task",
    description="Создает периодическую задачу по cron расписанию. Примеры cron: '0 10 * * *' (каждый день в 10:00), '*/5 * * * *' (каждые 5 минут), '0 9 * * 1' (каждый понедельник в 9:00)",
    tags=["scheduling"],
    parameters_model=ScheduleCronArgs,
)
async def schedule_cron_task(
    cron: str,
    content_type: str,
    content: str,
    tool_args: JsonObject | None = None,
    description: str | None = None,
    *,
    state: ExecutionState,
) -> str:
    """
    Создает периодическую задачу по cron.

    Аргументы:
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

    return f"Периодическая задача создана (schedule_task_id: {task.schedule_task_id}). Расписание: {cron}"


@tool(
    name="schedule_interval_task",
    description="Создает периодическую задачу с интервалом в минутах",
    tags=["scheduling"],
    parameters_model=ScheduleIntervalArgs,
)
async def schedule_interval_task(
    interval_minutes: int,
    content_type: str,
    content: str,
    tool_args: JsonObject | None = None,
    description: str | None = None,
    *,
    state: ExecutionState,
) -> str:
    """
    Создает периодическую задачу с интервалом.

    Аргументы:
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

    return (
        "Периодическая задача создана "
        f"(schedule_task_id: {task.schedule_task_id}). Интервал: каждые {interval_minutes} минут"
    )


@tool(
    name="schedule_one_time_task",
    description="Создает одноразовую задачу на конкретное время. Формат времени: ISO 8601 (например '2025-01-15T10:00:00')",
    tags=["scheduling"],
    parameters_model=ScheduleOneTimeArgs,
)
async def schedule_one_time_task(
    run_at: str,
    content_type: str,
    content: str,
    tool_args: JsonObject | None = None,
    description: str | None = None,
    *,
    state: ExecutionState,
) -> str:
    """
    Создает одноразовую задачу.

    Аргументы:
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

    return f"Одноразовая задача создана (schedule_task_id: {task.schedule_task_id}). Запуск: {run_at}"


@tool(
    name="list_scheduled_tasks",
    description="Показывает список запланированных задач текущей сессии",
    tags=["scheduling"],
    parameters_model=ListScheduledTasksArgs,
)
async def list_scheduled_tasks(
    *,
    state: ExecutionState,
) -> str:
    """
    Получает список scheduled tasks.

    Аргументы:
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
        schedule_type = task.schedule_type
        content_type = task.content_type
        status = task.status

        if schedule_type == "cron":
            schedule_info = f"cron: {task.cron}"
        elif schedule_type == "interval":
            schedule_info = f"каждые {task.interval_minutes} мин"
        elif schedule_type == "one_time":
            schedule_info = f"запуск: {task.run_at}"

        content_info = f"{content_type}: {task.content}"
        desc = f" - {task.description}" if task.description else ""

        lines.append(
            f"- [{task.schedule_task_id[:8]}] {schedule_info}, {content_info}, статус: {status}{desc}"
        )

    return "\n".join(lines)


@tool(
    name="cancel_scheduled_task",
    description="Отменяет запланированную задачу по её ID",
    tags=["scheduling"],
    parameters_model=CancelScheduledTaskArgs,
)
async def cancel_scheduled_task(
    schedule_task_id: str,
    *,
    state: ExecutionState,
) -> str:
    """
    Отменяет задачу.

    Аргументы:
        schedule_task_id: ID записи платформенного scheduler
        state: Состояние агента
    """
    service = get_schedule_service()

    success = await service.cancel_task(schedule_task_id)

    if success:
        state.scheduled_tasks = [
            t for t in state.scheduled_tasks if t.get("schedule_task_id") != schedule_task_id
        ]
        return f"Задача {schedule_task_id} отменена"
    else:
        return (
            f"Не удалось отменить задачу {schedule_task_id}. "
            "Возможно она уже выполнена или не существует."
        )
