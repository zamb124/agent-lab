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
)
from fastapi import APIRouter, Query
from google.protobuf.json_format import MessageToDict
from pydantic import Field

from apps.flows.di import Di
from apps.flows.realtime.durable_operations import (
    op_flows_durable_branches,
    op_flows_durable_fork,
    op_flows_durable_history,
    op_flows_durable_manual_patch,
    op_flows_durable_retry_from_failure,
    op_flows_durable_rewind,
    op_flows_durable_state_at,
    op_flows_sessions_state,
    op_flows_sessions_state_update,
)
from apps.flows.src.channels.types import FlowTaskResult
from apps.flows.src.durable_execution.models import WorkflowBranchResult
from apps.flows.src.models.durable_api import (
    DurableForkPayload,
    DurableHistoryPayload,
    DurableManualPatchPayload,
    DurableRetryPayload,
    DurableRewindPayload,
    DurableSessionIdPayload,
    DurableSessionStatePayload,
    DurableSessionStateUpdatePayload,
    DurableStateAtPayload,
    WorkflowBranchesResponse,
    WorkflowHistoryResponse,
)
from apps.flows.src.runtime.message_metadata import MESSAGE_SOURCE_TASK
from apps.flows.src.state import ExecutionState
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from core.a2a import platform_task_state_to_a2a, set_task_status_state, struct_from_mapping
from core.authz.models import AuthzObject
from core.context import get_context, require_active_company, require_context
from core.logging import get_logger
from core.models import StrictBaseModel
from core.tasks import enqueue
from core.types import JsonObject, require_json_object
from core.websocket import WsCommandError

logger = get_logger(__name__)

router = APIRouter(tags=["tasks"])


def _agent_text_message(text: str) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.ROLE_AGENT,
        parts=[Part(text=text)],
    )


class TaskSubmitRequest(StrictBaseModel):
    flow_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    branch_id: str = Field(default="default", min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    metadata: JsonObject = Field(default_factory=dict)


@router.post("/submit")
async def submit_task(request: TaskSubmitRequest, di: Di) -> JsonObject:
    """Отправляет задачу на выполнение. Возвращает A2A Task (ProtoJSON)."""
    task_id = str(uuid.uuid4())
    context = get_context()
    if context is None:
        raise ValueError("Context is required. Context must be created in middleware.")
    user_id = request.user_id if request.user_id is not None else context.user.user_id
    await di.authz_service.require_can_view(
        AuthzObject.flow(request.flow_id, company_id=require_active_company().company_id),
        user_id=user_id,
    )

    # session_id должен быть в формате flow_id:context_id
    if request.session_id is not None:
        session_id = request.session_id
        # Валидация формата session_id
        if ":" not in session_id:
            raise WsCommandError(
                "ws_invalid_payload",
                f"session_id must be in format 'flow_id:context_id', got: '{session_id}'",
                error_code="ws_invalid_payload",
            )
        # Извлекаем context_id из session_id
        context_id = session_id.split(":", 1)[1]
    else:
        # Создаем новый context_id и формируем session_id
        context_id = str(uuid.uuid4())
        session_id = f"{request.flow_id}:{context_id}"
    logger.info("flows.api.database_url", db_url=di.database.flows_url)

    state = await di.workflow_runtime.get_state(session_id)

    if state is None:
        branch_id = request.branch_id
        is_resume = False
        logger.info("flows.api.session_created", session_id=session_id)
    else:
        branch_id = state.branch_id
        is_resume = bool(state.interrupt)
        logger.info(
            "flows.api.session_existing",
            session_id=session_id,
            current_nodes=state.current_nodes,
            interrupt=bool(state.interrupt),
            is_resume=is_resume,
        )

    task = await enqueue(
        TASK_PROCESS_FLOW,
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
        logger.error("flows.api.task_failed", task_id=task_id, error=error_msg)
        if error_msg == "":
            error_msg = "Flow task failed"
        if "не найден" in error_msg:
            raise WsCommandError("not_found", error_msg, error_code="not_found")
        raise WsCommandError("internal", error_msg, error_code="internal")

    task_result = FlowTaskResult.model_validate(result.return_value)
    # None — flow припаркован на remote A2A-вызове: задача остаётся working.
    task_state = platform_task_state_to_a2a(task_result.task_state or "working")
    response_text = task_result.response

    # Breakpoint или interrupt — оба используют input_required
    if task_result.breakpoint_hit is not None:
        response_text = f"Breakpoint at node '{task_result.breakpoint_hit}'"
        task_state = TaskState.TASK_STATE_INPUT_REQUIRED
    elif task_result.interrupt is not None:
        response_text = task_result.interrupt.question
        task_state = TaskState.TASK_STATE_INPUT_REQUIRED

    task_status = TaskStatus(message=_agent_text_message(response_text))
    set_task_status_state(task_status, task_state)
    a2a_task = Task(
        id=task_id,
        context_id=session_id,
        status=task_status,
    )
    a2a_task.history.extend(
        [
            Message(
                message_id=str(uuid.uuid4()),
                role=Role.ROLE_USER,
                parts=[Part(text=request.content)],
                task_id=task_id,
                context_id=session_id,
                metadata=struct_from_mapping({"node_id": MESSAGE_SOURCE_TASK}),
            ),
            Message(
                message_id=str(uuid.uuid4()),
                role=Role.ROLE_AGENT,
                parts=[Part(text=response_text)],
                task_id=task_id,
                context_id=session_id,
                metadata=struct_from_mapping({"node_id": MESSAGE_SOURCE_TASK}),
            ),
        ]
    )

    return require_json_object(MessageToDict(a2a_task), "Task")


@router.get("/state", response_model=ExecutionState)
async def get_state(
    di: Di,
    session_id: str | None = None,
    context_id: str | None = None,
    flow_id: str | None = None,
) -> ExecutionState:
    return await op_flows_sessions_state(
        DurableSessionStatePayload(
            session_id=session_id,
            context_id=context_id,
            flow_id=flow_id,
        ),
        user=require_context().user,
        di=di,
    )


@router.put("/state", response_model=ExecutionState)
async def update_state(
    request: DurableSessionStateUpdatePayload,
    di: Di,
    session_id: str | None = None,
    context_id: str | None = None,
    flow_id: str | None = None,
) -> ExecutionState:
    return await op_flows_sessions_state_update(
        request.model_copy(
            update={
                "session_id": session_id if session_id is not None else request.session_id,
                "context_id": context_id if context_id is not None else request.context_id,
                "flow_id": flow_id if flow_id is not None else request.flow_id,
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/{session_id}/history", response_model=WorkflowHistoryResponse)
async def get_state_history(
    session_id: str,
    di: Di,
    execution_branch_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkflowHistoryResponse:
    return await op_flows_durable_history(
        DurableHistoryPayload(
            session_id=session_id,
            execution_branch_id=execution_branch_id,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/{session_id}/branches", response_model=WorkflowBranchesResponse)
async def list_execution_branches(
    session_id: str,
    di: Di,
) -> WorkflowBranchesResponse:
    return await op_flows_durable_branches(
        DurableSessionIdPayload(session_id=session_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{session_id}/fork", response_model=WorkflowBranchResult)
async def fork_state(
    session_id: str,
    request: DurableForkPayload,
    di: Di,
) -> WorkflowBranchResult:
    return await op_flows_durable_fork(
        request.model_copy(update={"session_id": session_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/{session_id}/rewind", response_model=WorkflowBranchResult)
async def rewind_state(
    session_id: str,
    request: DurableRewindPayload,
    di: Di,
) -> WorkflowBranchResult:
    return await op_flows_durable_rewind(
        request.model_copy(update={"session_id": session_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/{session_id}/manual-patch", response_model=WorkflowBranchResult)
async def manual_state_patch(
    session_id: str,
    request: DurableManualPatchPayload,
    di: Di,
) -> WorkflowBranchResult:
    return await op_flows_durable_manual_patch(
        request.model_copy(update={"session_id": session_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/{session_id}/retry-from-failure", response_model=WorkflowBranchResult)
async def retry_from_failure(
    session_id: str,
    request: DurableRetryPayload,
    di: Di,
) -> WorkflowBranchResult:
    return await op_flows_durable_retry_from_failure(
        request.model_copy(update={"session_id": session_id}),
        user=require_context().user,
        di=di,
    )


@router.get("/{session_id}/state-at/{sequence}", response_model=ExecutionState)
async def get_state_at_sequence(
    session_id: str,
    sequence: int,
    di: Di,
    execution_branch_id: str | None = None,
) -> ExecutionState:
    return await op_flows_durable_state_at(
        DurableStateAtPayload(
            session_id=session_id,
            sequence=sequence,
            execution_branch_id=execution_branch_id,
        ),
        user=require_context().user,
        di=di,
    )
