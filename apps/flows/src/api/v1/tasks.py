"""
API endpoints для задач через A2A типы.
"""

import uuid
from typing import Annotated

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
from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from apps.flows.src.channels.types import FlowTaskResult
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.durable_execution.models import (
    WorkflowBranchRecord,
    WorkflowEventRecord,
)
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

    state = await container.workflow_runtime.get_state(session_id)

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

    # Breakpoint или interrupt — оба используют input_required
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
    """Запрос ручного patch state для существующей durable workflow session."""

    state: ExecutionState


class TimeTravelRequest(StrictBaseModel):
    sequence: int = Field(..., ge=0)
    execution_branch_id: str | None = Field(default=None, min_length=1)


class ForkStateRequest(TimeTravelRequest):
    activate: bool = False


class ManualStatePatchRequest(TimeTravelRequest):
    state: ExecutionState
    activate: bool = True


class RetryFromFailureRequest(StrictBaseModel):
    failed_sequence: int | None = Field(default=None, ge=1)
    execution_branch_id: str | None = Field(default=None, min_length=1)


class WorkflowBranchOperationResponse(StrictBaseModel):
    execution_branch_id: str
    parent_execution_branch_id: str | None
    base_sequence: int
    base_state_hash: str | None
    reason: str
    event_id: str | None
    sequence: int
    state_hash: str
    snapshot_id: str


class WorkflowBranchesResponse(StrictBaseModel):
    branches: list[WorkflowBranchRecord]


class WorkflowHistoryResponse(StrictBaseModel):
    events: list[WorkflowEventRecord]
    total: int
    limit: int
    offset: int


@router.get("/state", response_model=ExecutionState)
async def get_state(
    container: ContainerDep,
    session_id: str | None = None,
    context_id: str | None = None,
    flow_id: str | None = None,
) -> ExecutionState:
    """
    Получает state по session_id или context_id+flow_id.

    Аргументы:
        session_id: ID сессии (альтернатива context_id+flow_id)
        context_id: ID контекста A2A
        flow_id: ID агента

    Возвращает:
        Снимок ExecutionState или, если записи нет, минимальный объект для UI чата:
        ``{"messages": [], "task_id": None}``.
    """

    if session_id:
        state = await container.workflow_runtime.get_state(session_id)
    elif context_id and flow_id:
        session_id = f"{flow_id}:{context_id}"
        state = await container.workflow_runtime.get_state(session_id)
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
    Применяет manual patch к существующей durable workflow-сессии.

    Аргументы:
        request: Тело запроса с целевой projection state
        session_id: ID сессии (альтернатива context_id+flow_id)
        context_id: ID контекста A2A для вычисления session_id
        flow_id: ID flow для вычисления session_id

    Возвращает:
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

    current = await container.workflow_runtime.get_state(session_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Workflow session not found")

    history, total = await container.workflow_runtime.get_state_history(
        session_id,
        limit=1,
        offset=0,
    )
    if total > 1:
        history, _ = await container.workflow_runtime.get_state_history(
            session_id,
            limit=1,
            offset=total - 1,
        )
    head_sequence = history[-1].sequence if history else 0
    _ = await container.workflow_runtime.patch_state_at_sequence(
        session_id,
        head_sequence,
        request.state,
    )
    updated_state = await container.workflow_runtime.get_state(session_id)

    if updated_state is None:
        raise HTTPException(status_code=500, detail="Failed to save state")

    return updated_state


@router.get("/{session_id}/history", response_model=WorkflowHistoryResponse)
async def get_state_history(
    session_id: str,
    container: ContainerDep,
    execution_branch_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkflowHistoryResponse:
    events, total = await container.workflow_runtime.get_state_history(
        session_id,
        execution_branch_id=execution_branch_id,
        limit=limit,
        offset=offset,
    )
    return WorkflowHistoryResponse(
        events=events,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{session_id}/branches", response_model=WorkflowBranchesResponse)
async def list_execution_branches(
    session_id: str,
    container: ContainerDep,
) -> WorkflowBranchesResponse:
    branches = await container.workflow_runtime.list_branches(session_id)
    return WorkflowBranchesResponse(branches=branches)


@router.post("/{session_id}/fork", response_model=WorkflowBranchOperationResponse)
async def fork_state(
    session_id: str,
    request: ForkStateRequest,
    container: ContainerDep,
) -> WorkflowBranchOperationResponse:
    result = await container.workflow_runtime.fork_state_at_sequence(
        session_id,
        request.sequence,
        execution_branch_id=request.execution_branch_id,
        activate=request.activate,
    )
    return WorkflowBranchOperationResponse.model_validate(result)


@router.post("/{session_id}/rewind", response_model=WorkflowBranchOperationResponse)
async def rewind_state(
    session_id: str,
    request: TimeTravelRequest,
    container: ContainerDep,
) -> WorkflowBranchOperationResponse:
    result = await container.workflow_runtime.rewind_to_sequence(
        session_id,
        request.sequence,
        execution_branch_id=request.execution_branch_id,
    )
    return WorkflowBranchOperationResponse.model_validate(result)


@router.post("/{session_id}/manual-patch", response_model=WorkflowBranchOperationResponse)
async def manual_state_patch(
    session_id: str,
    request: ManualStatePatchRequest,
    container: ContainerDep,
) -> WorkflowBranchOperationResponse:
    result = await container.workflow_runtime.patch_state_at_sequence(
        session_id,
        request.sequence,
        request.state,
        execution_branch_id=request.execution_branch_id,
        activate=request.activate,
    )
    return WorkflowBranchOperationResponse.model_validate(result)


@router.post("/{session_id}/retry-from-failure", response_model=WorkflowBranchOperationResponse)
async def retry_from_failure(
    session_id: str,
    request: RetryFromFailureRequest,
    container: ContainerDep,
) -> WorkflowBranchOperationResponse:
    result = await container.workflow_runtime.retry_from_failure(
        session_id,
        failed_sequence=request.failed_sequence,
        execution_branch_id=request.execution_branch_id,
    )
    return WorkflowBranchOperationResponse.model_validate(result)


@router.get("/{session_id}/state-at/{sequence}", response_model=ExecutionState)
async def get_state_at_sequence(
    session_id: str,
    sequence: int,
    container: ContainerDep,
    execution_branch_id: str | None = None,
) -> ExecutionState:
    state = await container.workflow_runtime.load_state_at_sequence(
        session_id,
        sequence,
        execution_branch_id=execution_branch_id,
    )
    if state is None:
        raise HTTPException(status_code=404, detail="State projection not found")
    return state
