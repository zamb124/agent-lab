"""
API endpoints для задач через A2A типы.
"""

import uuid

from a2a.types import (
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from a2a.utils.message import new_agent_text_message
from fastapi import APIRouter, HTTPException
from pydantic import Field

from apps.flows.src.channels.types import FlowTaskResult
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.runtime.message_metadata import MESSAGE_SOURCE_TASK
from apps.flows.src.tasks.flow_tasks import process_flow_task
from core.context import get_context
from core.logging import get_logger
from core.models import StrictBaseModel
from core.state import ExecutionState
from core.types import JsonObject

logger = get_logger(__name__)

router = APIRouter(tags=["tasks"])


class TaskSubmitRequest(StrictBaseModel):
    flow_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    branch_id: str = Field(default="default", min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    metadata: JsonObject = Field(default_factory=dict)


@router.post("/submit", response_model=Task)
async def submit_task(request: TaskSubmitRequest, container: ContainerDep) -> Task:
    """Отправляет задачу на выполнение. Возвращает A2A Task."""
    task_id = str(uuid.uuid4())
    context = get_context()
    if context is None:
        raise ValueError("Context is required. Context must be created in middleware.")
    user_id = request.user_id if request.user_id is not None else context.user.user_id

    # session_id должен быть в формате flow_id:context_id
    if request.session_id is not None:
        session_id = request.session_id
        # Валидация формата session_id
        if ":" not in session_id:
            raise HTTPException(
                status_code=400,
                detail=f"session_id must be in format 'flow_id:context_id', got: '{session_id}'",
            )
        # Извлекаем context_id из session_id
        context_id = session_id.split(":", 1)[1]
    else:
        # Создаем новый context_id и формируем session_id
        context_id = str(uuid.uuid4())
        session_id = f"{request.flow_id}:{context_id}"
    logger.info(f"API database_url: {container.db_url}")

    state = await container.state_manager.get_state(session_id)

    if state is None:
        branch_id = request.branch_id
        is_resume = False
        logger.info(f"API: New session {session_id}, is_resume=False")
    else:
        branch_id = state.branch_id
        is_resume = bool(state.interrupt)
        logger.info(
            f"API: Existing session {session_id}, "
            + f"current_nodes={state.current_nodes}, "
            + f"interrupt={bool(state.interrupt)}, "
            + f"is_resume={is_resume}"
        )

    task = await process_flow_task.kiq(
        flow_id=request.flow_id,
        session_id=session_id,
        user_id=user_id,
        content=request.content,
        branch_id=branch_id,
        channel="a2a",
        task_id=task_id,
        context_id=context_id,
        metadata=request.metadata,
        is_resume=is_resume,
        context_data=context.to_dict(),
    )

    result = await task.wait_result()

    if result.is_err:
        error_msg = str(result.error)
        logger.error(f"Task {task_id} failed: {error_msg}")
        if "не найден" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

    task_result = FlowTaskResult.model_validate(result.return_value)
    task_state = TaskState(task_result.task_state)
    response_text = task_result.response

    # Breakpoint или interrupt - оба используют input_required
    if task_result.breakpoint_hit is not None:
        response_text = f"Breakpoint at node '{task_result.breakpoint_hit}'"
        task_state = TaskState.input_required
    elif task_result.interrupt is not None:
        response_text = task_result.interrupt.question
        task_state = TaskState.input_required

    a2a_task = Task(
        id=task_id,
        context_id=session_id,
        status=TaskStatus(state=task_state, message=new_agent_text_message(response_text)),
        history=[
            Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=request.content))],
                task_id=task_id,
                context_id=session_id,
                metadata={"node_id": MESSAGE_SOURCE_TASK},
            ),
            Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[Part(root=TextPart(text=response_text))],
                task_id=task_id,
                context_id=session_id,
                metadata={"node_id": MESSAGE_SOURCE_TASK},
            ),
        ],
    )

    return a2a_task


class StateUpdateRequest(StrictBaseModel):
    """Запрос на обновление state"""

    state: ExecutionState


@router.get("/state", response_model=ExecutionState)
async def get_state(
    container: ContainerDep,
    session_id: str | None = None,
    context_id: str | None = None,
    flow_id: str | None = None,
) -> ExecutionState:
    """
    Получает state по session_id или context_id+flow_id.

    Args:
        session_id: ID сессии (альтернатива context_id+flow_id)
        context_id: ID контекста A2A
        flow_id: ID агента

    Returns:
        Снимок ExecutionState или, если записи нет, минимальный объект для UI чата:
        ``{"messages": [], "task_id": None}``.
    """

    if session_id:
        state = await container.state_manager.get_state(session_id)
    elif context_id and flow_id:
        session_id = f"{flow_id}:{context_id}"
        state = await container.state_manager.get_state(session_id)
    else:
        raise HTTPException(
            status_code=400,
            detail="Need session_id or context_id+flow_id"
        )

    if state is None:
        raise HTTPException(status_code=404, detail="State not found")

    return state


@router.put("/state", response_model=ExecutionState)
async def update_state(
    request: StateUpdateRequest,
    container: ContainerDep,
    session_id: str | None = None,
    context_id: str | None = None,
    flow_id: str | None = None,
) -> ExecutionState:
    """
    Сохраняет изменения state.

    Args:
        request: Тело запроса с обновленным state
        session_id: ID сессии (альтернатива context_id+flow_id)
        context_id: ID контекста A2A
        flow_id: ID агента

    Returns:
        Обновленный state
    """

    if session_id:
        pass
    elif context_id and flow_id:
        session_id = f"{flow_id}:{context_id}"
    else:
        raise HTTPException(
            status_code=400,
            detail="Need session_id or context_id+flow_id"
        )

    _ = await container.state_manager.save_state(session_id, request.state)
    updated_state = await container.state_manager.get_state(session_id)

    if updated_state is None:
        raise HTTPException(status_code=500, detail="Failed to save state")

    return updated_state
