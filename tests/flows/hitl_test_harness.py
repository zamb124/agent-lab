"""Общая парковка HITL-сессии для HTTP/channel тестов без моков."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.flows.di import FlowsDi
from apps.flows.src.models.hitl_schemas import HitlHandoffCommand
from core.state import ExecutionState
from core.state.interrupt import (
    HandoffMode,
    InterruptData,
    InterruptSystemContext,
    OperatorTaskInterrupt,
)
from core.types import JsonObject
from core.worktracker.models import UserActor


@dataclass(frozen=True, slots=True)
class ParkedHitlSession:
    flow_id: str
    context_id: str
    task_id: str
    session_id: str
    work_item_id: str
    queue_slug: str
    correlation_id: uuid.UUID
    mode: HandoffMode


def hitl_flow_create_payload(
    *,
    flow_id: str,
    queue_slug: str,
    mode: HandoffMode,
) -> JsonObject:
    return {
        "flow_id": flow_id,
        "name": flow_id,
        "entry": "hitl",
        "nodes": {
            "hitl": {
                "type": "hitl_node",
                "work_queue_slug": queue_slug,
                "handoff_task_title": "HITL",
                "handoff_user_message": "Ожидается оператор",
                "handoff_mode": mode.value,
            }
        },
        "edges": [{"from_node": "hitl", "to_node": None}],
    }


def llm_hitl_flow_create_payload(*, flow_id: str) -> JsonObject:
    """llm_node с calculator, ask_user и hitl_operator_task. Режим HITL задаёт вызов тула."""
    return {
        "flow_id": flow_id,
        "name": flow_id,
        "entry": "agent",
        "nodes": {
            "agent": {
                "type": "llm_node",
                "prompt": (
                    "Ты ассистент. Есть calculator, ask_user и hitl_operator_task. "
                    "Считай если нужно. Эскалация оператору — только через hitl_operator_task."
                ),
                "tools": ["calculator", "ask_user", "hitl_operator_task"],
            }
        },
        "edges": [{"from_node": "agent", "to_node": None}],
    }


async def attach_hitl_to_session(
    di: FlowsDi,
    unique_id: str,
    *,
    mode: HandoffMode,
    owner_user_id: str,
    session_id: str,
    queue_slug: str | None = None,
) -> ParkedHitlSession:
    state = await di.workflow_runtime.get_state(session_id)
    if state is None:
        raise RuntimeError(f"HITL session {session_id} is missing")
    resolved_slug = queue_slug
    if resolved_slug is None:
        resolved_slug = f"hitl-q-{unique_id}"
        await di.work_item_service.create_queue(
            company_id="system",
            name=f"HITL {unique_id}",
            slug=resolved_slug,
            creator=UserActor(user_id=owner_user_id),
        )
    command_key = f"hitl:test:{unique_id}"
    command = HitlHandoffCommand(
        correlation_id=uuid.uuid5(uuid.NAMESPACE_URL, command_key),
        idempotency_key=command_key,
        execution_branch_id="default",
        node_schedule_sequence=1,
        node_id="hitl",
        tool_call_id=None,
    )
    _cid, work_item_id = await di.node_constructor.hitl_work_item_service.register_handoff(
        state,
        question="Ожидается оператор",
        task_title="HITL",
        assignee_queue_slug=resolved_slug,
        handoff_mode=mode,
        command=command,
    )
    parked = state.model_copy(
        update={
            "interrupt": InterruptData(
                body=OperatorTaskInterrupt(
                    question="Ожидается оператор",
                    task_title="HITL",
                    assignee_queue=resolved_slug,
                    handoff_mode=mode,
                    work_item_id=work_item_id,
                    handoff_command_id=command.idempotency_key,
                    execution_branch_id="default",
                    node_schedule_sequence=1,
                    node_id="hitl",
                ),
                system=InterruptSystemContext(
                    task_id=state.task_id, context_id=state.context_id
                ),
                correlation_id=command.correlation_id,
            )
        }
    )
    await di.workflow_runtime.save_state(session_id, parked, snapshot=True)
    return ParkedHitlSession(
        flow_id=parked.session_flow_id,
        context_id=parked.context_id,
        task_id=parked.task_id,
        session_id=session_id,
        work_item_id=work_item_id,
        queue_slug=resolved_slug,
        correlation_id=command.correlation_id,
        mode=mode,
    )


async def park_hitl_session(
    di: FlowsDi,
    unique_id: str,
    *,
    mode: HandoffMode,
    owner_user_id: str,
    flow_id: str | None = None,
) -> ParkedHitlSession:
    queue_slug = f"hitl-q-{unique_id}"
    await di.work_item_service.create_queue(
        company_id="system",
        name=f"HITL {unique_id}",
        slug=queue_slug,
        creator=UserActor(user_id=owner_user_id),
    )
    resolved_flow_id = flow_id if flow_id is not None else f"hitl_flow_{unique_id}"
    context_id = f"ctx-{unique_id}"
    task_id = f"task-{unique_id}"
    session_id = f"{resolved_flow_id}:{context_id}"
    state = ExecutionState(
        task_id=task_id,
        context_id=context_id,
        user_id=owner_user_id,
        session_id=session_id,
        branch_id="default",
        content="wait",
    )
    await di.workflow_runtime.save_state(session_id, state, snapshot=True)
    return await attach_hitl_to_session(
        di,
        unique_id,
        mode=mode,
        owner_user_id=owner_user_id,
        session_id=session_id,
        queue_slug=queue_slug,
    )
