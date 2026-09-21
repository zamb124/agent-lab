"""
Tools для управления scheduled tasks.

Позволяют агентам создавать и управлять отложенными задачами.
Тонкие обёртки над FlowScheduleClient.
"""

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.clients.flow_schedule_client import FlowScheduleClient
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.scheduling.scheduling_ids import extract_ids_from_state
from core.scheduler.models import ContentType, ScheduledTaskInfo
from core.state import ExecutionState
from core.types import JsonObject, require_json_object


def _extract_ids_from_state(state: ExecutionState) -> tuple[str, str, str]:
    return extract_ids_from_state(state)


def _task_json(task: ScheduledTaskInfo) -> JsonObject:
    return require_json_object(task.model_dump(mode="json"), "scheduled_task")


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
    effects=["create"],
    confirmation_floor="preview",
)
async def schedule_cron_task(
    cron: str,
    content_type: str,
    content: str,
    tool_args: JsonObject | None = None,
    description: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    client = FlowScheduleClient()
    ct = ContentType(content_type)
    flow_id, session_id, user_id = _extract_ids_from_state(state)

    task = await client.schedule_cron_task(
        flow_id=flow_id,
        session_id=session_id,
        user_id=user_id,
        cron=cron,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )

    payload = _task_json(task)
    state.scheduled_tasks.append(payload)
    return payload


@tool(
    name="schedule_interval_task",
    description="Создает периодическую задачу с интервалом в минутах",
    tags=["scheduling"],
    parameters_model=ScheduleIntervalArgs,
    effects=["create"],
    confirmation_floor="preview",
)
async def schedule_interval_task(
    interval_minutes: int,
    content_type: str,
    content: str,
    tool_args: JsonObject | None = None,
    description: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    client = FlowScheduleClient()
    ct = ContentType(content_type)
    flow_id, session_id, user_id = _extract_ids_from_state(state)

    task = await client.schedule_interval_task(
        flow_id=flow_id,
        session_id=session_id,
        user_id=user_id,
        interval_minutes=interval_minutes,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )

    payload = _task_json(task)
    state.scheduled_tasks.append(payload)
    return payload


@tool(
    name="schedule_one_time_task",
    description="Создает одноразовую задачу на конкретное время. Формат времени: ISO 8601 (например '2025-01-15T10:00:00')",
    tags=["scheduling"],
    parameters_model=ScheduleOneTimeArgs,
    effects=["create"],
    confirmation_floor="preview",
)
async def schedule_one_time_task(
    run_at: str,
    content_type: str,
    content: str,
    tool_args: JsonObject | None = None,
    description: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    client = FlowScheduleClient()
    ct = ContentType(content_type)
    run_at_dt = datetime.fromisoformat(run_at)
    flow_id, session_id, user_id = _extract_ids_from_state(state)

    task = await client.schedule_one_time_task(
        flow_id=flow_id,
        session_id=session_id,
        user_id=user_id,
        run_at=run_at_dt,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )

    payload = _task_json(task)
    state.scheduled_tasks.append(payload)
    return payload


@tool(
    name="list_scheduled_tasks",
    description="Показывает список запланированных задач текущей сессии",
    tags=["scheduling"],
    parameters_model=ListScheduledTasksArgs,
    effects=["read"],
)
async def list_scheduled_tasks(
    *,
    state: ExecutionState,
) -> JsonObject:
    client = FlowScheduleClient()
    _, session_id, _ = _extract_ids_from_state(state)
    tasks = await client.list_tasks(session_id=session_id)
    return {
        "items": [_task_json(task) for task in tasks],
    }


@tool(
    name="cancel_scheduled_task",
    description="Отменяет запланированную задачу по её ID",
    tags=["scheduling"],
    parameters_model=CancelScheduledTaskArgs,
    effects=["delete"],
    confirmation_floor="preview",
)
async def cancel_scheduled_task(
    schedule_task_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    client = FlowScheduleClient()
    success = await client.cancel_task(schedule_task_id)
    if not success:
        raise ValueError(
            f"Не удалось отменить задачу {schedule_task_id}. "
            + "Возможно она уже выполнена или не существует."
        )

    state.scheduled_tasks = [
        t for t in state.scheduled_tasks if t.get("schedule_task_id") != schedule_task_id
    ]
    return {
        "schedule_task_id": schedule_task_id,
        "cancelled": True,
    }
