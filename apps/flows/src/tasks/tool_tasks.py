"""
TaskIQ задачи для выполнения tools.

Сериализация ExecutionState происходит на границе очереди (TaskIQ).
Внутри задачи работаем с ExecutionState объектом.
"""

from __future__ import annotations

from typing import Any

from apps.flows.src.container import get_container
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows_worker.broker import broker
from core.context import clear_context, get_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.state.interrupt import interrupt_to_response_dict

logger = get_logger(__name__)


@broker.task(task_name="execute_tool", queue_name="flows_worker")
async def execute_tool(
    tool_id_or_config: Any,
    args: dict[str, Any],
    state_dict: dict[str, Any],
    context_data: dict[str, Any] | None = None,
):
    """
    Выполняет tool через TaskIQ.

    Args:
        tool_id_or_config: ID tool (str) или inline конфиг (dict)
        args: Аргументы вызова
        state_dict: Сериализованный ExecutionState (граница TaskIQ)
        context_data: Сериализованный Context (как у process_flow_task) для репозиториев с company_id

    Returns:
        Dict с результатом (сериализуется обратно для TaskIQ)
    """
    previous_context = None
    if context_data is not None:
        previous_context = get_context()
        set_context(Context.from_dict(context_data))

    container = get_container()

    if isinstance(tool_id_or_config, str):
        tool_id = tool_id_or_config
        tool = await container.tool_registry.create_tool({"tool_id": tool_id})
    else:
        tool_id = tool_id_or_config.get("tool_id", "unknown")
        tool = await container.tool_registry.create_tool(tool_id_or_config)
    logger.debug(f"Executing tool: {tool_id}")

    from core.state import ExecutionState
    tool_state = ExecutionState.model_validate(state_dict)

    try:
        try:
            result = await tool.run(args, tool_state)
        except FlowInterrupt as e:
            nested = tool_state.nested_states
            path = [item.model_dump() for item in tool_state.interrupt_path]
            logger.info(
                f"Tool {tool_id} interrupt: {e.question[:50]}..., nested_keys={list(nested.keys())}, path_len={len(path)}"
            )
            InterruptManager.apply_interrupt(
                tool_state,
                e.body,
                e.tool_call,
                getattr(e, "correlation_id", None),
            )
            packed = tool_state.interrupt
            if packed is None:
                raise RuntimeError("execute_tool: apply_interrupt не выставил interrupt")
            return {
                "tool_id": tool_id,
                "result": None,
                "interrupt": interrupt_to_response_dict(packed),
                "nested_states": nested,
                "interrupt_path": path,
            }

        logger.debug(f"Tool {tool_id} completed")

        return {
            "tool_id": tool_id,
            "result": result,
            "nested_states": tool_state.nested_states,
        }
    finally:
        if context_data is not None:
            if previous_context is not None:
                set_context(previous_context)
            else:
                clear_context()
