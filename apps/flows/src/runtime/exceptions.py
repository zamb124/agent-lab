"""
Исключения агентов.
"""

from typing import Any, Dict, Optional


class FlowInterrupt(Exception):
    """Исключение для прерывания агента с вопросом пользователю."""

    def __init__(
        self,
        question: str,
        tool_call: dict | None = None,
        flow_id: str = "",
    ):
        self.question = question
        self.tool_call = tool_call
        self.flow_id = flow_id
        super().__init__(question)


class BreakpointInterrupt(Exception):
    """
    Исключение для остановки выполнения агента на breakpoint.
    
    Выбрасывается когда агент достигает ноды с установленным breakpoint.
    Сохраняет snapshot state для отображения в UI.
    """

    def __init__(
        self,
        node_id: str,
        node_type: str,
        state_snapshot: Dict[str, Any],
        flow_id: str = "",
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.state_snapshot = state_snapshot
        self.flow_id = flow_id
        super().__init__(f"Breakpoint hit at node '{node_id}'")


class ToolExecutionError(Exception):
    """Ошибка выполнения tool."""

    def __init__(self, message: str, error: Optional[Exception] = None):
        self.message = message
        self.error = error
        super().__init__(message)


class NodeCallLimitError(Exception):
    """Превышен лимит вызовов ноды."""

    def __init__(self, message: str, limit: int):
        self.message = message
        self.limit = limit
        super().__init__(message)

