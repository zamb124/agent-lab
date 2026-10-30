"""Ход пользователя (текст или ui-action) во время HITL single_reply не возобновляет граф."""

from __future__ import annotations

import uuid

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.durable_execution import (
    UserInputAppliedPayload,
    WorkflowEventType,
    create_initial_state,
)
from apps.flows.src.state.interrupt import (
    HandoffMode,
    InterruptData,
    InterruptSystemContext,
    OperatorTaskInterrupt,
)
from core.ui_document.protocol import FlowUIActionMessage


def _operator_interrupt(*, unique_id: str, task_id: str, context_id: str) -> InterruptData:
    return InterruptData(
        body=OperatorTaskInterrupt(
            question="Ожидается оператор",
            task_title="HITL",
            assignee_queue="example_hitl",
            handoff_mode=HandoffMode.SINGLE_REPLY,
            handoff_command_id=f"hitl:{unique_id}:node:hitl",
            execution_branch_id="default",
            node_schedule_sequence=1,
            node_id="hitl",
        ),
        system=InterruptSystemContext(task_id=task_id, context_id=context_id),
        correlation_id=uuid.uuid4(),
    )


async def _park_single_reply_session(
    di: FlowsDi, unique_id: str
) -> tuple[str, str, str]:
    flow_id = f"flow-{unique_id}"
    context_id = f"ctx-{unique_id}"
    task_id = f"task-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    state = create_initial_state(
        task_id=task_id,
        context_id=context_id,
        user_id="user_hitl",
        session_id=session_id,
        content="wait",
    )
    parked = state.model_copy(
        update={
            "interrupt": _operator_interrupt(
                unique_id=unique_id, task_id=task_id, context_id=context_id
            )
        }
    )
    await di.workflow_runtime.save_state(
        session_id,
        parked,
        event_type=WorkflowEventType.user_input_applied,
        payload=UserInputAppliedPayload(
            task_id=parked.task_id,
            context_id=parked.context_id,
            is_resume=False,
        ),
        snapshot=True,
    )
    return flow_id, context_id, task_id


@pytest.mark.asyncio
async def test_plain_a2a_user_message_rejected_during_hitl_single_reply(
    app, di, unique_id: str
) -> None:
    _ = app
    flow_id, context_id, task_id = await _park_single_reply_session(di, unique_id)
    channel = A2AChannel(flow_id, variables_service=di.variables_service, authz_service=di.authz_service, workflow_runtime=di.node_constructor.workflow_runtime, redis_client=di.node_constructor.redis_client, handoff_orchestrator_service=di.handoff_orchestrator_service, flow_factory=di.flow_factory, tool_registry=di.tool_registry, projection_service=di.a2a_task_projection_service, shared_storage=di.shared_storage, channel_registry=di.channel_registry, mail_service=di.mail_service, flow_ui_share_service=di.flow_ui_share_service, hitl_conversation_service=di.hitl_conversation_service, files_service=di.files_service)
    with pytest.raises(ValueError, match="cannot resume HITL single_reply"):
        await channel._prepare_task_params(
            content="пинг пользователя",
            context_id=context_id,
            task_id=task_id,
        )


@pytest.mark.asyncio
async def test_ui_action_rejected_during_hitl_single_reply(app, di, unique_id: str) -> None:
    _ = app
    flow_id, context_id, task_id = await _park_single_reply_session(di, unique_id)
    channel = A2AChannel(flow_id, variables_service=di.variables_service, authz_service=di.authz_service, workflow_runtime=di.node_constructor.workflow_runtime, redis_client=di.node_constructor.redis_client, handoff_orchestrator_service=di.handoff_orchestrator_service, flow_factory=di.flow_factory, tool_registry=di.tool_registry, projection_service=di.a2a_task_projection_service, shared_storage=di.shared_storage, channel_registry=di.channel_registry, mail_service=di.mail_service, flow_ui_share_service=di.flow_ui_share_service, hitl_conversation_service=di.hitl_conversation_service, files_service=di.files_service)
    with pytest.raises(ValueError, match="cannot resume HITL single_reply"):
        await channel._prepare_task_params(
            content="",
            context_id=context_id,
            task_id=task_id,
            ui_action=FlowUIActionMessage(
                action="send", source="conversation", payload={"text": "пинг пользователя"}
            ),
        )
