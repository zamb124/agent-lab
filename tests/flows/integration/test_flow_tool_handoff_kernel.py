from __future__ import annotations

import pytest

from apps.flows.src.channels.types import PreparedTaskParams
from apps.flows.src.models import Edge, FlowConfig, FlowToolReference
from apps.flows.src.models.enums import NodeToolCallType
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.tools.handoff_tools import handback_to_parent, handoff_to_flow
from core.state import ChildWorkflowLink
from core.state.interrupt import HandoffInterrupt, InterruptKind
from tests.flows.durable_runtime_harness import workflow_state

pytestmark = [
    pytest.mark.no_test_doubles,
    pytest.mark.timeout(120, func_only=True),
]


def _prepared_params(parent_flow_id: str, context_id: str) -> PreparedTaskParams:
    return PreparedTaskParams(
        task_id=f"task-{context_id}",
        context_id=context_id,
        session_id=f"{parent_flow_id}:{context_id}",
        content="Нужен профильный агент",
        branch_id="default",
        is_resume=False,
        files_data=[],
        message=None,
        metadata=None,
        user_id=f"user-{context_id}",
    )


@pytest.mark.asyncio
async def test_flow_tool_wrapper_emits_typed_handoff_without_llm_or_test_double(
    container,
    unique_id: str,
) -> None:
    child_flow_id = f"strict-child-{unique_id}"
    ref = FlowToolReference(
        tool_id="coach",
        flow_id=child_flow_id,
        branch_id="default",
        call_type=NodeToolCallType.HANDOFF,
        name="Профильный консультант",
    )
    tool = await container.tool_registry.materialize(ref)
    state = workflow_state(
        flow_id=f"strict-parent-{unique_id}",
        unique_id=unique_id,
        content="Передай запрос",
    )

    with pytest.raises(FlowInterrupt) as raised:
        await tool.run({"request": "Разбери сложный случай"}, state)

    body = raised.value.body
    assert isinstance(body, HandoffInterrupt)
    assert body.kind == InterruptKind.HANDOFF
    assert body.target_flow_id == child_flow_id
    assert body.target_branch_id == "default"
    assert body.target_name == "Профильный консультант"
    assert body.variables == {"request": "Разбери сложный случай"}


@pytest.mark.asyncio
async def test_handoff_kernel_creates_and_routes_real_child_state_without_test_doubles(
    container,
    unique_id: str,
) -> None:
    parent_flow_id = f"strict-parent-route-{unique_id}"
    child_flow_id = f"strict-child-route-{unique_id}"
    await container.flow_repository.set(
        FlowConfig(
            flow_id=child_flow_id,
            name="Профильный консультант",
            entry="done",
            nodes={"done": {"type": "channel", "channel": "email", "action": "send"}},
            edges=[Edge(from_node="done", to_node=None)],
        )
    )
    parent_state = workflow_state(
        flow_id=parent_flow_id,
        unique_id=unique_id,
        content="Исходная реплика пользователя",
        variables={"private_parent_value": "must-not-leak"},
    )
    params = _prepared_params(parent_flow_id, parent_state.context_id)

    with pytest.raises(FlowInterrupt) as raised:
        await handoff_to_flow.run(
            {
                "target_flow_id": child_flow_id,
                "target_branch_id": "default",
                "variables": {"case_id": "CASE-42"},
                "reason": "Нужна специализация",
            },
            parent_state,
        )
    body = raised.value.body
    assert isinstance(body, HandoffInterrupt)

    orchestrator = container.handoff_orchestrator_service
    validated = await orchestrator.validate_handoff_target(body)
    assert validated.target_name == "Профильный консультант"
    child_depth = orchestrator.assert_handoff_depth_allowed(parent_state)
    child_context_id, child_session_id = orchestrator.build_child_session_ids(
        parent_state.context_id,
        child_flow_id,
    )
    child_state = await orchestrator.ensure_child_state(
        parent_state=parent_state,
        parent_params=params,
        body=validated,
        child_session_id=child_session_id,
        child_context_id=child_context_id,
        child_depth=child_depth,
    )

    assert child_state.session_id == child_session_id
    assert child_state.context_id == child_context_id
    assert child_state.content == "Исходная реплика пользователя"
    assert child_state.variables == {"case_id": "CASE-42"}
    assert "private_parent_value" not in child_state.variables
    assert child_state.handoff_parent_session_id == parent_state.session_id
    assert child_state.handoff_depth == 1

    InterruptManager.apply_handoff_interrupt(parent_state, validated, child_session_id)
    parent_state.child_workflows[child_session_id] = ChildWorkflowLink(
        node_id="coach",
        child_session_id=child_session_id,
        child_flow_id=child_flow_id,
        child_flow_branch_id="default",
        child_execution_branch_id="initial",
        parent_session_id=parent_state.session_id,
        parent_execution_branch_id="initial",
        parent_node_schedule_sequence=1,
        status="running",
        handoff=True,
    )
    routing = orchestrator.resolve_active_handoff_child(parent_state)
    assert routing is not None
    assert routing.child_session_id == child_session_id
    assert routing.child_flow_id == child_flow_id
    assert routing.child_branch_id == "default"

    routed_params = _prepared_params(parent_flow_id, parent_state.context_id)
    routed_params.is_handoff_user_reply = True
    routed_params.handoff_child_session_id = routing.child_session_id
    routed_params.handoff_child_flow_id = routing.child_flow_id
    routed_params.handoff_child_branch_id = routing.child_branch_id
    target = await orchestrator.resolve_execution_target(
        parent_flow_id=parent_flow_id,
        params=routed_params,
    )
    assert target.flow_id == child_flow_id
    assert target.session_id == child_session_id
    assert target.context_id == child_context_id
    assert target.branch_id == "default"

    await handback_to_parent.run(
        {
            "response": "Случай обработан",
            "variables": {"resolution_id": "RES-7"},
        },
        child_state,
    )
    assert child_state.terminal_task_state == "handback"
    assert child_state.response == "Случай обработан"
    assert child_state.handback_return_variables == {"resolution_id": "RES-7"}
