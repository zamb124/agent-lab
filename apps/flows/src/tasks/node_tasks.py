"""
TaskIQ task для выполнения нод.

Сериализация ExecutionState происходит на границе очереди (TaskIQ).
"""

from __future__ import annotations

from typing import Any, Dict

from apps.flows_worker.broker import broker
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task(task_name="execute_node", queue_name="flows_worker")
async def execute_node(
    node_id: str,
    node_config: Dict[str, Any],
    state_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Выполняет ноду в воркере.

    Args:
        node_id: ID ноды
        node_config: Конфигурация ноды
        state_dict: Сериализованный ExecutionState (граница TaskIQ)

    Returns:
        Сериализованный ExecutionState
    """
    from apps.flows.src.runtime.nodes import create_node
    from core.state import ExecutionState

    state = ExecutionState.model_validate(state_dict)
    node = await create_node(node_id, node_config)

    logger.debug(f"Executing node {node_id} (type={node_config.get('type', 'unknown')})")

    # Вызываем напрямую, не через .kiq() чтобы избежать рекурсии
    result_state = await node.run(state)

    return result_state.model_dump(exclude_none=False)
