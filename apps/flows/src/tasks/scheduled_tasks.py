"""
Задачи для выполнения scheduled tasks.
"""

import uuid
from datetime import datetime, timezone

from apps.flows.config import get_settings
from apps.flows.src.channels.types import PreparedTaskParams
from apps.flows.src.container import FlowContainer, get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.services.execution_identity import resolve_execution_context
from apps.flows.src.tasks.task_names import TASK_EXECUTE_SCHEDULED
from apps.flows.src.tools.base import ToolArguments
from core.context import set_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import (
    flow_employee_curator_user_ids,
    is_flow_employee,
    is_flow_employee_user_id,
)
from core.logging import get_logger
from core.scheduler import get_schedule_source
from core.scheduler.models import ContentType, PlatformScheduleType, ScheduledTaskStatus
from core.state import ExecutionState
from core.tasks import platform_task
from core.types import JsonObject, require_json_object, require_json_value
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


async def _resolve_escalation_targets(container: FlowContainer, user_id: str) -> list[str]:
    """Кому слать эскалацию/уведомление о завершении.

    Обычный пользователь — самому себе. Если таргет — flow-сотрудник (фоновый
    запуск без человека-инициатора), эскалация уходит его кураторам.
    """
    if not is_flow_employee_user_id(user_id):
        return [user_id]
    employee = await container.user_repository.get(user_id)
    if employee is None or not is_flow_employee(employee):
        return [user_id]
    curators = flow_employee_curator_user_ids(employee)
    return curators if curators else [user_id]


@platform_task(TASK_EXECUTE_SCHEDULED)
async def execute_scheduled_task(
    schedule_task_id: str,
    flow_id: str,
    session_id: str,
    user_id: str,
    content_type: str,
    content: str,
    tool_args: ToolArguments | None = None,
    description: str | None = None,
    company_id: str | None = None,
) -> JsonObject:
    """
    Выполняет scheduled task.

    Вызывается TaskIQ scheduler когда наступает время выполнения.

    При ошибке:
    - Помечает задачу как FAILED
    - Удаляет schedule из Redis (чтобы не повторялась)

    Аргументы:
        schedule_task_id: ID записи платформенного scheduler
        flow_id: ID flow
        session_id: ID сессии
        user_id: ID пользователя
        content_type: Тип ("message" или "tool_call")
        content: Сообщение или имя tool
        tool_args: Аргументы для tool_call
        description: Описание задачи

    Возвращает:
        Результат выполнения
    """
    logger.info(
        "Executing scheduled task: schedule_task_id=%s, content_type=%s, description=%s",
        schedule_task_id,
        content_type,
        description,
    )
    task_content_type = ContentType(content_type)

    container = get_container()

    effective_flow_id = flow_id
    if not effective_flow_id:
        raise ValueError("flow_id is required for scheduled task")
    if company_id is None:
        raise ValueError("company_id is required for scheduled task")

    scheduler_repo = container.scheduler_task_repository

    # Источник правды — платформенная таблица scheduler_tasks (shared БД).
    task_info = await scheduler_repo.get(
        company_id=company_id, schedule_task_id=schedule_task_id
    )

    company = await container.company_repository.get(company_id)
    if company is None:
        raise ValueError(f"scheduled task: company {company_id} not found")
    initiator_user = await container.user_repository.get(user_id)
    if initiator_user is None:
        raise ValueError(f"scheduled task: user {user_id} not found")
    initiator_context = build_job_context(
        company=company,
        user=initiator_user,
        host="",
        trace_id="",
        session_id=session_id,
        channel="scheduler",
    )
    initiator_context.flow_id = effective_flow_id

    flow_config = await container.flow_repository.get(effective_flow_id)
    if flow_config is None:
        raise ValueError(f"scheduled task: flow {effective_flow_id} not found")
    execution = await resolve_execution_context(
        as_flow_runtime_container(container),
        flow_config=flow_config,
        initiator_context=initiator_context,
    )
    set_context(execution.context)
    actor_user_id = execution.context.user.user_id

    try:
        if task_content_type == ContentType.MESSAGE:
            result = await _execute_message_task(
                container=container,
                flow_id=effective_flow_id,
                session_id=session_id,
                user_id=actor_user_id,
                initiator_user_id=user_id,
                content=content,
            )
        elif task_content_type == ContentType.TOOL_CALL:
            if tool_args is None:
                raise ValueError("tool_args is required for scheduled tool_call")
            result = await _execute_tool_call_task(
                container=container,
                session_id=session_id,
                user_id=actor_user_id,
                tool_name=content,
                tool_args=tool_args,
            )
        else:
            raise ValueError(f"Unknown content_type: {content_type}")

        logger.info("Scheduled task executed: schedule_task_id=%s", schedule_task_id)
        scheduler_status = ScheduledTaskStatus.PENDING
        if task_info and task_info.schedule_type == PlatformScheduleType.ONE_TIME:
            scheduler_status = ScheduledTaskStatus.EXECUTED
        _ = await scheduler_repo.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=scheduler_status,
            last_run_at=datetime.now(timezone.utc),
            error_message=None,
        )
        return result

    except Exception as e:
        logger.error("Scheduled task failed: schedule_task_id=%s, error=%s", schedule_task_id, e)
        _ = await scheduler_repo.update_status(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
            status=ScheduledTaskStatus.FAILED,
            error_message=str(e),
        )

        if task_info and task_info.schedule_id:
            try:
                settings = get_settings()
                source = get_schedule_source(settings.database.redis_url)
                await source.startup()
                _ = await source.delete_schedule(task_info.schedule_id)
                logger.info(f"Deleted failed schedule from Redis: {task_info.schedule_id}")
            except Exception as del_error:
                logger.warning(f"Failed to delete schedule from Redis: {del_error}")

        raise


async def _execute_message_task(
    container: FlowContainer,
    flow_id: str,
    session_id: str,
    user_id: str,
    content: str,
    initiator_user_id: str | None = None,
) -> JsonObject:
    """Выполняет message task - отправляет сообщение агенту."""
    channel_instance = container.get_channel("a2a", flow_id)

    task_id = str(uuid.uuid4())

    params = PreparedTaskParams(
        task_id=task_id,
        context_id=session_id,
        session_id=session_id,
        content=content,
        branch_id="default",
        is_resume=False,
        files_data=[],
        message=None,
        metadata={"scheduled": True},
        user_id=user_id,
        initiator_user_id=initiator_user_id,
    )

    result = await channel_instance.process_task(params)

    # Уведомление о завершении шлётся инициатору (создателю расписания), не актору-агенту.
    # Если инициатор сам flow-сотрудник (фоновый запуск), эскалация уходит его кураторам.
    notify_targets = await _resolve_escalation_targets(container, initiator_user_id or user_id)
    if result.task_state == "completed":
        final_response = result.response
        preview = final_response[:100] + ("..." if len(final_response) > 100 else "")

        for notify_target in notify_targets:
            await notify_user(
                user_id=notify_target,
                notification=Notification(
                    type=NotificationType.TASK_COMPLETED,
                    title="Задача выполнена",
                    message=preview,
                    service="flows",
                    action_url=f"/flows/{flow_id}/session/{session_id}",
                    data={
                        "flow_id": flow_id,
                        "session_id": session_id,
                        "task_id": task_id,
                    },
                ),
            )

    return require_json_object(
        result.model_dump(mode="json", exclude_none=False),
        "scheduled.message_task.result",
    )


async def _execute_tool_call_task(
    container: FlowContainer,
    session_id: str,
    user_id: str,
    tool_name: str,
    tool_args: ToolArguments,
) -> JsonObject:
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
        "result": require_json_value(result, "scheduled.tool_call.result"),
    }
