"""
TaskIQ task для выполнения нод.

Сериализация ExecutionState происходит на границе очереди (TaskIQ).
"""

from __future__ import annotations

from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.runtime.nodes import create_node
from apps.flows.src.tasks.task_names import TASK_EXECUTE_NODE
from apps.flows_worker.broker import broker
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

    Args:
        node_id: ID ноды
        node_config: Конфигурация ноды
        state_dict: Сериализованный ExecutionState (граница TaskIQ)

    Returns:
        Сериализованный ExecutionState
    """
    container = get_container()
    state = ExecutionState.model_validate(state_dict)
    node = await create_node(
        node_id,
        node_config,
        container=as_flow_runtime_container(container),
    )

    logger.debug(f"Executing node {node_id} (type={node_config.get('type', 'unknown')})")

    # Вызываем напрямую, не через .kiq() чтобы избежать рекурсии
    result_state = await node.execute(state)

    return require_json_object(
        result_state.model_dump(mode="json", exclude_none=False),
        "execute_node.result_state",
    )
