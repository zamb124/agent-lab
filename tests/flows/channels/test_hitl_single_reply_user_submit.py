"""User submit during HITL single_reply must not resume the graph."""

from __future__ import annotations

import uuid

import pytest

from apps.flows.src.a2a.interaction_parser import parse_flow_ui_command
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.durable_execution import (
    UserInputAppliedPayload,
    WorkflowEventType,
    create_initial_state,
)
from core.a2a import PLATFORM_UI_BOOTSTRAP_ACTION, PLATFORM_UI_SUBMIT_ACTION
from core.state.interrupt import (
    HandoffMode,
    InterruptData,
    InterruptSystemContext,
    OperatorTaskInterrupt,
)
from tests.flows._flow_ui_session import flow_ui_command_message


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
    container: FlowRuntimeContainer, unique_id: str
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
    await container.workflow_runtime.save_state(
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
    app, container, unique_id: str
) -> None:
    _ = app
    flow_id, context_id, task_id = await _park_single_reply_session(container, unique_id)
    channel = A2AChannel(flow_id, container=container)
    with pytest.raises(ValueError, match="не может резюмировать HITL single_reply"):
        await channel._prepare_task_params(
            content="пинг пользователя",
            context_id=context_id,
            task_id=task_id,
        )


@pytest.mark.asyncio
async def test_flow_ui_submit_rejected_during_hitl_single_reply(
    app, container, unique_id: str
) -> None:
    _ = app
    flow_id, context_id, task_id = await _park_single_reply_session(container, unique_id)
    command = parse_flow_ui_command(
        flow_ui_command_message(
            action=PLATFORM_UI_SUBMIT_ACTION,
            context_id=context_id,
            action_id=f"action-{unique_id}",
            revision=1,
            message_value="пинг пользователя",
        )
    )
    assert command is not None
    channel = A2AChannel(flow_id, container=container)
    with pytest.raises(ValueError, match="не может резюмировать HITL single_reply"):
        await channel._prepare_task_params(
            content="пинг пользователя",
            context_id=context_id,
            task_id=task_id,
            flow_ui_command=command,
        )


@pytest.mark.asyncio
async def test_flow_ui_bootstrap_allowed_during_hitl_single_reply(
    app, container, unique_id: str
) -> None:
    _ = app
    flow_id, context_id, task_id = await _park_single_reply_session(container, unique_id)
    command = parse_flow_ui_command(
        flow_ui_command_message(
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"boot-{unique_id}",
        )
    )
    assert command is not None
    channel = A2AChannel(flow_id, container=container)
    prepared = await channel._prepare_task_params(
        content="",
        context_id=context_id,
        task_id=task_id,
        flow_ui_command=command,
    )
    assert prepared.flow_ui_command is command
    assert prepared.is_takeover_user_reply is False
