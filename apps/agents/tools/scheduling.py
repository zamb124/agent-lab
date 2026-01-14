"""
Tools для управления scheduled tasks.

Позволяют агентам создавать и управлять отложенными задачами.
"""

from datetime import datetime
from typing import Optional, Tuple

from apps.agents.src.container import get_container
from apps.agents.src.tools import tool
from core.scheduler.models import ContentType


def _extract_ids_from_state(state: Optional[dict]) -> Tuple[str, str, str]:
    """
    Извлекает agent_id, session_id, user_id из state.
    
    session_id ОБЯЗАТЕЛЕН и ВСЕГДА в формате 'agent_id:context_id'.
    Валидация формата происходит в ExecutionState.
    """
    if not state:
        raise ValueError("state is required for scheduling tools")
    
    session_id = state.get("session_id")
    if not session_id:
        raise ValueError("session_id is required in state for scheduling tools")
    
    if ":" not in session_id:
        raise ValueError(
            f"session_id must be in format 'agent_id:context_id', got: '{session_id}'"
        )
    
    agent_id = session_id.split(":")[0]
    user_id = state.get("user_id") or ""
    
    return agent_id, session_id, user_id


@tool(
    name="schedule_cron_task",
    description="Создает периодическую задачу по cron расписанию. Примеры cron: '0 10 * * *' (каждый день в 10:00), '*/5 * * * *' (каждые 5 минут), '0 9 * * 1' (каждый понедельник в 9:00)",
    tags=["scheduling"],
)
async def schedule_cron_task(
    cron: str,
    content_type: str,
    content: str,
    tool_args: Optional[dict] = None,
    description: Optional[str] = None,
    state: Optional[dict] = None,
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
    container = get_container()
    service = container.schedule_service
    
    ct = ContentType(content_type)
    agent_id, session_id, user_id = _extract_ids_from_state(state)
    
    task = await service.schedule_cron_task(
        agent_id=agent_id,
        session_id=session_id,
        user_id=user_id,
        cron=cron,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )
    
    if state:
        scheduled_tasks = state.get("scheduled_tasks", [])
        scheduled_tasks.append(task.model_dump())
        state["scheduled_tasks"] = scheduled_tasks
    
    return f"Периодическая задача создана (ID: {task.id}). Расписание: {cron}"


@tool(
    name="schedule_interval_task",
    description="Создает периодическую задачу с интервалом в минутах",
    tags=["scheduling"],
)
async def schedule_interval_task(
    interval_minutes: int,
    content_type: str,
    content: str,
    tool_args: Optional[dict] = None,
    description: Optional[str] = None,
    state: Optional[dict] = None,
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
    container = get_container()
    service = container.schedule_service
    
    ct = ContentType(content_type)
    agent_id, session_id, user_id = _extract_ids_from_state(state)
    
    task = await service.schedule_interval_task(
        agent_id=agent_id,
        session_id=session_id,
        user_id=user_id,
        interval_minutes=interval_minutes,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )
    
    if state:
        scheduled_tasks = state.get("scheduled_tasks", [])
        scheduled_tasks.append(task.model_dump())
        state["scheduled_tasks"] = scheduled_tasks
    
    return f"Периодическая задача создана (ID: {task.id}). Интервал: каждые {interval_minutes} минут"


@tool(
    name="schedule_one_time_task",
    description="Создает одноразовую задачу на конкретное время. Формат времени: ISO 8601 (например '2025-01-15T10:00:00')",
    tags=["scheduling"],
)
async def schedule_one_time_task(
    run_at: str,
    content_type: str,
    content: str,
    tool_args: Optional[dict] = None,
    description: Optional[str] = None,
    state: Optional[dict] = None,
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
    container = get_container()
    service = container.schedule_service
    
    ct = ContentType(content_type)
    run_at_dt = datetime.fromisoformat(run_at)
    agent_id, session_id, user_id = _extract_ids_from_state(state)
    
    task = await service.schedule_one_time_task(
        agent_id=agent_id,
        session_id=session_id,
        user_id=user_id,
        run_at=run_at_dt,
        content_type=ct,
        content=content,
        tool_args=tool_args,
        description=description,
    )
    
    if state:
        scheduled_tasks = state.get("scheduled_tasks", [])
        scheduled_tasks.append(task.model_dump())
        state["scheduled_tasks"] = scheduled_tasks
    
    return f"Одноразовая задача создана (ID: {task.id}). Запуск: {run_at}"


@tool(
    name="list_scheduled_tasks",
    description="Показывает список запланированных задач текущей сессии",
    tags=["scheduling"],
)
async def list_scheduled_tasks(
    state: Optional[dict] = None,
) -> str:
    """
    Получает список scheduled tasks.
    
    Args:
        state: Состояние агента
    """
    container = get_container()
    service = container.schedule_service
    
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
)
async def cancel_scheduled_task(
    task_id: str,
    state: Optional[dict] = None,
) -> str:
    """
    Отменяет задачу.
    
    Args:
        task_id: ID задачи
        state: Состояние агента
    """
    container = get_container()
    service = container.schedule_service
    
    success = await service.cancel_task(task_id)
    
    if success:
        if state:
            scheduled_tasks = state.get("scheduled_tasks", [])
            state["scheduled_tasks"] = [t for t in scheduled_tasks if t.get("id") != task_id]
        return f"Задача {task_id} отменена"
    else:
        return f"Не удалось отменить задачу {task_id}. Возможно она уже выполнена или не существует."

