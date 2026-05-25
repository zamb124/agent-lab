from __future__ import annotations

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.durable_execution import (
    NodeCompletedPayload,
    NodeScheduledPayload,
    NodeWriteRecordedPayload,
    RunStartedPayload,
    SuperstepStartedPayload,
    WorkflowEventType,
    build_state_delta,
)
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import BaseNode
from core.state import ExecutionState
from core.types import JsonObject


def workflow_state(
    *,
    flow_id: str,
    unique_id: str,
    branch_id: str = "default",
    content: str | None = None,
    **extra: object,
) -> ExecutionState:
    context_id = f"context-{unique_id}"
    payload: dict[str, object] = {
        "task_id": f"task-{unique_id}",
        "context_id": context_id,
        "user_id": f"user-{unique_id}",
        "session_id": f"{flow_id}:{context_id}",
        "branch_id": branch_id,
    }
    if content is not None:
        payload["content"] = content
    payload.update(extra)
    return ExecutionState.model_validate(payload)


async def ensure_workflow_started(
    *,
    container: FlowRuntimeContainer,
    state: ExecutionState,
    flow_id: str,
    branch_id: str,
) -> None:
    if state.session_flow_id != flow_id:
        raise RuntimeError(
            f"Workflow state session flow {state.session_flow_id!r} does not match {flow_id!r}"
        )
    position = await container.workflow_runtime.get_active_execution_position(state.session_id)
    if position is not None:
        return
    _ = await container.workflow_runtime.record_state_event(
        state.session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(
            flow_id=flow_id,
            branch_id=branch_id,
            task_id=state.task_id,
            flow_config_version=state.flow_config_version,
        ),
        snapshot=True,
    )


async def run_flow(
    *,
    container: FlowRuntimeContainer,
    flow: Flow,
    state: ExecutionState,
) -> ExecutionState:
    await ensure_workflow_started(
        container=container,
        state=state,
        flow_id=flow.flow_id,
        branch_id=state.branch_id,
    )
    return await flow.run(state)


async def run_node(
    *,
    container: FlowRuntimeContainer,
    node: BaseNode,
    state: ExecutionState,
) -> ExecutionState:
    node_type = _node_type(node.config)
    await ensure_workflow_started(
        container=container,
        state=state,
        flow_id=state.session_flow_id,
        branch_id=state.branch_id,
    )
    state.current_nodes = [node.node_id]
    superstep_event = await container.workflow_runtime.record_state_event(
        state.session_id,
        state,
        event_type=WorkflowEventType.superstep_started,
        payload=SuperstepStartedPayload(current_nodes=[node.node_id]),
    )
    scheduled_event = await container.workflow_runtime.record_state_event(
        state.session_id,
        state,
        event_type=WorkflowEventType.node_scheduled,
        payload=NodeScheduledPayload(
            node_id=node.node_id,
            node_type=node_type,
            current_nodes=[node.node_id],
        ),
    )
    state.attach_durable_node_context(
        execution_branch_id=scheduled_event.execution_branch_id,
        node_schedule_sequence=scheduled_event.sequence,
        superstep_sequence=superstep_event.sequence,
    )
    before_state = ExecutionState.model_validate(
        state.model_dump(mode="python", exclude_none=False)
    )
    result_state = await node.run(state)
    _ = await container.workflow_runtime.record_state_event(
        result_state.session_id,
        result_state,
        event_type=WorkflowEventType.node_write_recorded,
        payload=NodeWriteRecordedPayload(
            node_id=node.node_id,
            node_type=node_type,
            state_delta=build_state_delta(before_state, result_state),
        ),
    )
    _ = await container.workflow_runtime.record_state_event(
        result_state.session_id,
        result_state,
        event_type=WorkflowEventType.node_completed,
        payload=NodeCompletedPayload(node_id=node.node_id, node_type=node_type),
    )
    return result_state


def _node_type(config: JsonObject) -> str:
    node_type = config.get("type")
    if not isinstance(node_type, str) or not node_type.strip():
        raise ValueError("node.config.type must be a non-empty string")
    return node_type
