"""
TaskIQ task для выполнения нод.

Сериализация ExecutionState происходит на границе очереди (TaskIQ).
"""

from __future__ import annotations

from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.durable_execution import (
    NodeCompletedPayload,
    NodeScheduledPayload,
    NodeWriteRecordedPayload,
    RunStartedPayload,
    SuperstepStartedPayload,
    WorkflowEventType,
    build_state_delta,
)
from apps.flows.src.runtime.nodes import create_node
from apps.flows.src.tasks.task_names import TASK_EXECUTE_NODE
from apps.flows_worker.broker_core import broker
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)


@broker.task(task_name=TASK_EXECUTE_NODE, queue_name="flows_worker")
async def execute_node(
    node_id: str,
    node_config: JsonObject,
    state_dict: JsonObject,
) -> JsonObject:
    """
    Выполняет ноду в воркере.

    Аргументы:
        node_id: ID ноды
        node_config: Конфигурация ноды
        state_dict: Сериализованный ExecutionState (граница TaskIQ)

    Возвращает:
        Сериализованный ExecutionState
    """
    container = get_container()
    state = ExecutionState.model_validate(state_dict)
    node = await create_node(
        node_id,
        node_config,
        container=as_flow_runtime_container(container),
    )

    raw_node_type = node_config.get("type")
    if not isinstance(raw_node_type, str) or not raw_node_type.strip():
        raise ValueError("execute_node.node_config.type must be a non-empty string")
    node_type = raw_node_type.strip()

    runtime = container.workflow_runtime
    position = await runtime.get_active_execution_position(state.session_id)
    if position is None:
        _ = await runtime.record_state_event(
            state.session_id,
            state,
            event_type=WorkflowEventType.run_started,
            payload=RunStartedPayload(
                flow_id=state.session_flow_id,
                branch_id=state.branch_id,
                task_id=state.task_id,
                flow_config_version=state.flow_config_version,
            ),
            snapshot=True,
        )
    state.current_nodes = [node_id]
    superstep_event = await runtime.record_state_event(
        state.session_id,
        state,
        event_type=WorkflowEventType.superstep_started,
        payload=SuperstepStartedPayload(current_nodes=[node_id]),
    )
    scheduled_event = await runtime.record_state_event(
        state.session_id,
        state,
        event_type=WorkflowEventType.node_scheduled,
        payload=NodeScheduledPayload(
            node_id=node_id,
            node_type=node_type,
            current_nodes=[node_id],
        ),
    )
    state.attach_durable_node_context(
        execution_branch_id=scheduled_event.execution_branch_id,
        node_schedule_sequence=scheduled_event.sequence,
        superstep_sequence=superstep_event.sequence,
    )

    logger.debug(f"Executing node {node_id} (type={node_type})")
    before_state = ExecutionState.model_validate(
        state.model_dump(mode="python", exclude_none=False)
    )
    result_state = await node.execute(state)
    _ = await runtime.record_state_event(
        result_state.session_id,
        result_state,
        event_type=WorkflowEventType.node_write_recorded,
        payload=NodeWriteRecordedPayload(
            node_id=node_id,
            node_type=node_type,
            state_delta=build_state_delta(before_state, result_state),
        ),
    )
    _ = await runtime.record_state_event(
        result_state.session_id,
        result_state,
        event_type=WorkflowEventType.node_completed,
        payload=NodeCompletedPayload(node_id=node_id, node_type=node_type),
    )

    return require_json_object(
        result_state.model_dump(mode="json", exclude_none=False),
        "execute_node.result_state",
    )
