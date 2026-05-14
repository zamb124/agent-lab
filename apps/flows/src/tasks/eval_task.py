"""
TaskIQ task для выполнения inline кода.

Сериализация ExecutionState происходит на границе очереди (TaskIQ).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from apps.flows.src.eval import safe_eval
from apps.flows_worker.broker import broker
from core.context import get_context
from core.logging import get_logger

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)


@broker.task(queue_name="flows_worker")
async def execute_inline_code(code: str, state_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет inline код через safe_eval.

    Args:
        code: Код функции
        state_dict: Сериализованный ExecutionState (граница TaskIQ)

    Returns:
        Сериализованный ExecutionState

    Raises:
        SafeEvalError: При ошибке выполнения
    """
    from core.state import ExecutionState

    state = ExecutionState.model_validate(state_dict)
    logger.debug("Executing inline code")

    context = get_context()
    result = await safe_eval(code, state, context=context)

    # Сериализация для возврата через TaskIQ
    if isinstance(result, ExecutionState):
        return result.model_dump(exclude_none=False)
    elif isinstance(result, dict):
        return result
    else:
        raise ValueError(f"Inline code must return ExecutionState or dict, got {type(result)}")


async def run_inline_code(code: str, state: 'ExecutionState') -> 'ExecutionState':
    """
    Выполняет inline код напрямую в текущем процессе.
    Это позволяет использовать контекст выполнения (context, variables).

    Args:
        code: Код функции
        state: ExecutionState

    Returns:
        ExecutionState (результат выполнения)
    """


    context = get_context()
    result = await safe_eval(code, state, context=context)
    return result
