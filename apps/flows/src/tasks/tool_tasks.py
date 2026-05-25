"""
TaskIQ задачи для выполнения tools.

Сериализация ExecutionState происходит на границе очереди (TaskIQ).
Внутри задачи работаем с ExecutionState объектом.
"""

from __future__ import annotations

from apps.flows.src.container import get_container
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.tasks.task_names import TASK_EXECUTE_TOOL
from apps.flows.src.tools.base import ToolArguments
from apps.flows.src.tools.registry import ToolMaterializeInput
from apps.flows_worker.broker import broker
from core.context import clear_context, get_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.state import ExecutionState
from core.state.interrupt import interrupt_to_response_dict
from core.types import JsonObject, require_json_array, require_json_object

logger = get_logger(__name__)


@broker.task(task_name=TASK_EXECUTE_TOOL, queue_name="flows_worker")
async def execute_tool(
    tool_config: ToolMaterializeInput,
    args: ToolArguments,
    state_dict: JsonObject,
    context_data: JsonObject | None = None,
) -> JsonObject:
    """
    Выполняет tool через TaskIQ.

    Args:
        tool_config: Inline tool config, ToolReference или NodeConfig
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
    tool = await container.tool_registry.create_tool(tool_config)
    tool_id = tool.name
    logger.debug(f"Executing tool: {tool_id}")

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
                e.correlation_id,
            )
            packed = tool_state.interrupt
            if packed is None:
                raise RuntimeError("execute_tool: apply_interrupt не выставил interrupt")
            state_payload = require_json_object(
                tool_state.model_dump(mode="json"),
                "execute_tool.state",
            )
            return {
                "tool_id": tool_id,
                "result": None,
                "interrupt": require_json_object(
                    interrupt_to_response_dict(packed),
                    "execute_tool.interrupt",
                ),
                "nested_states": require_json_object(
                    state_payload["nested_states"],
                    "execute_tool.nested_states",
                ),
                "interrupt_path": require_json_array(
                    state_payload["interrupt_path"],
                    "execute_tool.interrupt_path",
                ),
            }

        logger.debug(f"Tool {tool_id} completed")
        state_payload = require_json_object(
            tool_state.model_dump(mode="json"),
            "execute_tool.state",
        )

        return {
            "tool_id": tool_id,
            "result": result,
            "nested_states": require_json_object(
                state_payload["nested_states"],
                "execute_tool.nested_states",
            ),
        }
    finally:
        if context_data is not None:
            if previous_context is not None:
                set_context(previous_context)
            else:
                clear_context()
