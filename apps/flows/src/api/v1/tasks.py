"""
API endpoints для задач через A2A типы.
"""

import uuid
from typing import Any, Dict, Optional

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
from pydantic import BaseModel

from apps.flows.src.container import get_container
from core.logging import get_logger
from apps.flows.src.tasks.flow_tasks import process_flow_task
from core.context import Context, User, get_context
from core.state import ExecutionState

logger = get_logger(__name__)

router = APIRouter(tags=["tasks"])


class TaskSubmitRequest(BaseModel):
    flow_id: str
    content: str
    skill_id: str = "default"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


@router.post("/submit")
async def submit_task(request: TaskSubmitRequest) -> Dict[str, Any]:
    """Отправляет задачу на выполнение. Возвращает A2A Task."""
    task_id = str(uuid.uuid4())
    user_id = request.user_id or task_id
    
    # session_id должен быть в формате flow_id:context_id
    if request.session_id:
        session_id = request.session_id
        # Валидация формата session_id
        if ":" not in session_id:
            raise HTTPException(
                status_code=400,
                detail=f"session_id must be in format 'flow_id:context_id', got: '{session_id}'"
            )
        # Извлекаем context_id из session_id
        context_id = session_id.split(":", 1)[1]
    else:
        # Создаем новый context_id и формируем session_id
        context_id = str(uuid.uuid4())
        session_id = f"{request.flow_id}:{context_id}"

    container = get_container()
    logger.info(f"API database_url: {container.db_url}")

    state = await container.state_manager.get_state(session_id)

    if state is None:
        skill_id = request.skill_id
        is_resume = False
        logger.info(f"API: New session {session_id}, is_resume=False")
    else:
        skill_id = state.skill_id
        is_resume = bool(state.interrupt)
        logger.info(
            f"API: Existing session {session_id}, "
            f"current_nodes={state.current_nodes}, "
            f"interrupt={bool(state.interrupt)}, "
            f"is_resume={is_resume}"
        )

    # Получаем Context из middleware (middleware всегда создает Context)
    context = get_context()
    if context is None:
        raise ValueError("Context is required. Context must be created in middleware.")

    task = await process_flow_task.kiq(
        flow_id=request.flow_id,
        session_id=session_id,
        user_id=user_id,
        content=request.content,
        skill_id=skill_id,
        channel="a2a",
        task_id=task_id,
        context_id=context_id,
        metadata=request.metadata,
        is_resume=is_resume,
        context_data=context.model_dump(exclude_none=False),
    )

    result = await task.wait_result()

    if result.is_err:
        error_msg = str(result.error)
        logger.error(f"Task {task_id} failed: {error_msg}")
        if "не найден" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

    task_result = result.return_value

    # Breakpoint или interrupt - оба используют input_required
    breakpoint_hit = task_result.get("breakpoint_hit")
    interrupt_data = task_result.get("interrupt")
    
    if breakpoint_hit:
        response_text = f"Breakpoint at node '{breakpoint_hit}'"
        task_state = TaskState.input_required
    elif interrupt_data:
        if isinstance(interrupt_data, dict):
            response_text = interrupt_data.get("question", "")
        else:
            response_text = str(interrupt_data)
        task_state = TaskState.input_required
    else:
        response_text = task_result.get("response", "")
        task_state = TaskState.completed

    a2a_task = Task(
        id=task_id,
        contextId=session_id,
        status=TaskStatus(state=task_state, message=new_agent_text_message(response_text)),
        history=[
            Message(
                messageId=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=request.content))],
                taskId=task_id,
                contextId=session_id,
            ),
            Message(
                messageId=str(uuid.uuid4()),
                role=Role.agent,
                parts=[Part(root=TextPart(text=response_text))],
                taskId=task_id,
                contextId=session_id,
            ),
        ],
    )

    return a2a_task.model_dump(by_alias=True, exclude_none=True)


class StateUpdateRequest(BaseModel):
    """Запрос на обновление state"""
    state: Dict[str, Any]


@router.get("/state")
async def get_state(
    session_id: Optional[str] = None,
    context_id: Optional[str] = None,
    flow_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Получает state по session_id или context_id+flow_id.
    
    Args:
        session_id: ID сессии (альтернатива context_id+flow_id)
        context_id: ID контекста A2A
        flow_id: ID агента
    
    Returns:
        State как словарь со всеми полями (включая системные)
    """
    container = get_container()
    
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
    
    return state.model_dump()


@router.put("/state")
async def update_state(
    request: StateUpdateRequest,
    session_id: Optional[str] = None,
    context_id: Optional[str] = None,
    flow_id: Optional[str] = None,
) -> Dict[str, Any]:
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
    container = get_container()
    
    if session_id:
        pass
    elif context_id and flow_id:
        session_id = f"{flow_id}:{context_id}"
    else:
        raise HTTPException(
            status_code=400,
            detail="Need session_id or context_id+flow_id"
        )
    
    state_obj = ExecutionState.model_validate(request.state)
    await container.state_manager.save_state(session_id, state_obj)
    updated_state = await container.state_manager.get_state(session_id)
    
    if updated_state is None:
        raise HTTPException(status_code=500, detail="Failed to save state")
    
    return updated_state.model_dump()
