"""
Задачи для выполнения scheduled tasks.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from apps.flows.src.channels.types import PreparedTaskParams
from apps.flows.config import get_settings
from apps.flows.src.container import get_container
from core.state import ExecutionState
from core.context import Context, set_context
from core.logging import get_logger
from core.scheduler import get_schedule_source
from core.scheduler.repository import SchedulerTaskRepository
from core.scheduler.models import ScheduledTaskStatus
from apps.flows_worker.broker import broker

logger = get_logger(__name__)


@broker.task(task_name="execute_scheduled_task", queue_name="flows_worker")
async def execute_scheduled_task(
    scheduled_task_id: str,
    flow_id: str,
    session_id: str,
    user_id: str,
    task_type: str,
    payload: Dict[str, Any],
    scheduler_task_id: str | None = None,
    company_id: str | None = None,
) -> Dict[str, Any]:
    """
    Выполняет scheduled task.
    
    Вызывается TaskIQ scheduler когда наступает время выполнения.
    
    При ошибке:
    - Помечает задачу как FAILED
    - Удаляет schedule из Redis (чтобы не повторялась)
    
    Args:
        scheduled_task_id: ID scheduled task в БД
        flow_id: ID flow
        session_id: ID сессии
        user_id: ID пользователя
        task_type: Тип ("message" или "tool_call")
        payload: Данные задачи (content, tool_args)
        
    Returns:
        Результат выполнения
    """
    logger.info(f"Executing scheduled task: id={scheduled_task_id}, type={task_type}")
    
    container = get_container()
    scheduled_task_repo = container.scheduled_task_repository
    
    # Получаем задачу из БД
    task_info = await scheduled_task_repo.get_by_id(scheduled_task_id)
    
    # Извлекаем flow_id из session_id если не передан (формат: flow_id:context_id)
    effective_flow_id = flow_id
    if not effective_flow_id and session_id and ":" in session_id:
        effective_flow_id = session_id.split(":")[0]
    
    content = payload.get("content", "")
    tool_args = payload.get("tool_args")
    
    effective_scheduler_task_id = scheduler_task_id or scheduled_task_id
    effective_company_id = company_id or "system"

    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required for scheduler metadata updates")
    scheduler_repo = SchedulerTaskRepository(db_url=settings.database.shared_url)

    from core.models.identity_models import User, Company
    
    context = Context(
        user=User(user_id=user_id, name="Scheduler"),
        active_company=Company(company_id=effective_company_id, name=effective_company_id),
        session_id=session_id,
        flow_id=effective_flow_id,
        channel="scheduler",
    )
    set_context(context)
    
    try:
        if task_type == "message":
            result = await _execute_message_task(
                container=container,
                flow_id=effective_flow_id,
                session_id=session_id,
                user_id=user_id,
                content=content,
                context=context,
            )
        elif task_type == "tool_call":
            result = await _execute_tool_call_task(
                container=container,
                flow_id=effective_flow_id,
                session_id=session_id,
                user_id=user_id,
                tool_name=content,
                tool_args=tool_args or {},
                context=context,
            )
        else:
            raise ValueError(f"Unknown task_type: {task_type}")
        
        # Успех - обновляем статус для one-time tasks
        if task_info:
            schedule_type = task_info.schedule_type if isinstance(task_info.schedule_type, str) else task_info.schedule_type.value
            if schedule_type == "one_time":
                await scheduled_task_repo.update_status(
                    scheduled_task_id,
                    ScheduledTaskStatus.EXECUTED
                )
        
        logger.info(f"Scheduled task executed: id={scheduled_task_id}")
        scheduler_status = ScheduledTaskStatus.PENDING
        if task_info:
            schedule_type = task_info.schedule_type if isinstance(task_info.schedule_type, str) else task_info.schedule_type.value
            if schedule_type == "one_time":
                scheduler_status = ScheduledTaskStatus.EXECUTED
        await scheduler_repo.update_status(
            company_id=effective_company_id,
            schedule_task_id=effective_scheduler_task_id,
            status=scheduler_status,
            last_run_at=datetime.now(timezone.utc),
            error_message=None,
        )
        return result
        
    except Exception as e:
        logger.error(f"Scheduled task failed: id={scheduled_task_id}, error={e}")
        
        # Помечаем как FAILED
        await scheduled_task_repo.update_status(
            scheduled_task_id,
            ScheduledTaskStatus.FAILED,
            error_message=str(e),
        )
        await scheduler_repo.update_status(
            company_id=effective_company_id,
            schedule_task_id=effective_scheduler_task_id,
            status=ScheduledTaskStatus.FAILED,
            error_message=str(e),
        )
        
        # Удаляем schedule из Redis чтобы не повторялась
        if task_info and task_info.schedule_id:
            try:
                settings = get_settings()
                source = get_schedule_source(settings.database.redis_url)
                await source.startup()
                await source.delete_schedule(task_info.schedule_id)
                logger.info(f"Deleted failed schedule from Redis: {task_info.schedule_id}")
            except Exception as del_error:
                logger.warning(f"Failed to delete schedule from Redis: {del_error}")
        
        # Пробрасываем ошибку дальше (TaskIQ пометит task как failed)
        raise


async def _execute_message_task(
    container,
    flow_id: str,
    session_id: str,
    user_id: str,
    content: str,
    context: Context,
) -> Dict[str, Any]:
    """Выполняет message task - отправляет сообщение агенту."""
    channel_instance = container.get_channel("a2a", flow_id)
    
    task_id = str(uuid.uuid4())
    
    params = PreparedTaskParams(
        task_id=task_id,
        context_id=session_id,
        session_id=session_id,
        content=content,
        skill_id="default",
        is_resume=False,
        files_data=[],
        message=None,
        metadata={"scheduled": True},
        user_id=user_id,
    )
    
    result = await channel_instance.process_task(params)
    
    # Отправляем уведомление о завершении задачи (WebSocket + Web Push)
    if result.get("status") == "completed":
        from core.websocket.publisher import notify_user, Notification, NotificationType
        
        final_response = result.get("response", "")
        preview = final_response[:100] + ("..." if len(final_response) > 100 else "")
        
        await notify_user(
            user_id=user_id,
            notification=Notification(
                type=NotificationType.TASK_COMPLETED,
                title="Задача выполнена",
                message=preview,
                service="flows",
                action_url=f"/chat/{flow_id}?session={session_id}",
                data={
                    "flow_id": flow_id,
                    "session_id": session_id,
                    "task_id": task_id
                }
            )
        )
    
    return result


async def _execute_tool_call_task(
    container,
    flow_id: str,
    session_id: str,
    user_id: str,
    tool_name: str,
    tool_args: Dict[str, Any],
    context: Context,
) -> Dict[str, Any]:
    """Выполняет tool_call task — только инлайн-тулы из tool_repository."""
    tool = await container.tool_registry.create_tool({"tool_id": tool_name})
    
    state = ExecutionState.create(
        task_id=str(uuid.uuid4()),
        context_id=session_id.split(":")[1] if ":" in session_id else session_id,
        user_id=user_id,
        session_id=session_id,
    )
    
    result = await tool.run(tool_args, state)
    
    return {
        "tool": tool_name,
        "args": tool_args,
        "result": result,
    }

