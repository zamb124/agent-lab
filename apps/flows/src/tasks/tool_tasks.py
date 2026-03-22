"""
TaskIQ задачи для выполнения tools.

Сериализация ExecutionState происходит на границе очереди (TaskIQ).
Внутри задачи работаем с ExecutionState объектом.
"""

from __future__ import annotations

import copy
from typing import Any, Dict

from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.container import get_container
from core.logging import get_logger

from apps.broker.broker import broker

logger = get_logger(__name__)


@broker.task(task_name="execute_tool", queue_name="default")
async def execute_tool(
    tool_id_or_config: Any,
    args: Dict[str, Any],
    state_dict: Dict[str, Any],
):
    """
    Выполняет tool через TaskIQ.

    Args:
        tool_id_or_config: ID tool (str) или inline конфиг (dict)
        args: Аргументы вызова
        state_dict: Сериализованный ExecutionState (граница TaskIQ)

    Returns:
        Dict с результатом (сериализуется обратно для TaskIQ)
    """
    container = get_container()
    
    if isinstance(tool_id_or_config, str):
        tool_id = tool_id_or_config
        # Сначала проверяем зарегистрированные builtin tools (FunctionTool)
        tool = container.tool_registry.get(tool_id)
        if not tool:
            # Если не найден - создаем InlineTool
            tool = await container.tool_registry.create_tool({"tool_id": tool_id})
    else:
        tool_id = tool_id_or_config.get("tool_id", "unknown")
        # Для inline config сначала проверяем builtin
        tool = container.tool_registry.get(tool_id)
        if not tool:
            tool = await container.tool_registry.create_tool(tool_id_or_config)
    logger.debug(f"Executing tool: {tool_id}")

    from core.state import ExecutionState
    tool_state = ExecutionState.model_validate(state_dict)

    try:
        result = await tool.run(args, tool_state)
    except FlowInterrupt as e:
        # FlowInterrupt НЕ происходит в execute_tool - это функция для tools
        # Это исключение ловится где-то выше в стеке
        nested = tool_state.nested_states
        path = [item.model_dump() for item in tool_state.interrupt_path]
        logger.info(
            f"Tool {tool_id} interrupt: {e.question[:50]}..., nested_keys={list(nested.keys())}, path_len={len(path)}"
        )
        return {
            "tool_id": tool_id,
            "result": None,
            "interrupt": {"question": e.question},
            "nested_states": nested,
            "interrupt_path": path,
        }

    logger.debug(f"Tool {tool_id} completed")

    # Сериализация для возврата через TaskIQ
    return {
        "tool_id": tool_id,
        "result": result,
        "nested_states": tool_state.nested_states,
    }
