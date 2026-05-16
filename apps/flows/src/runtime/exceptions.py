"""
Исключения агентов.
"""

from typing import Any
from uuid import UUID

from core.state.interrupt import (
    InterruptBody,
    UserMessageInterrupt,
    interrupt_body_public_question,
)


class FlowInterrupt(Exception):
    """Прерывание выполнения с типизированным телом interrupt (HITL)."""

    def __init__(
        self,
        question: str | None = None,
        *,
        body: InterruptBody | None = None,
        tool_call: dict[str, Any] | None = None,
        flow_id: str = "",
        correlation_id: UUID | None = None,
    ):
        if body is not None:
            if question is not None:
                raise ValueError("FlowInterrupt: нельзя передавать одновременно body и question")
            self.body: InterruptBody = body
        elif question is not None:
            if not isinstance(question, str) or not question.strip():
                raise ValueError("FlowInterrupt: question должен быть непустой строкой")
            self.body = UserMessageInterrupt(question=question.strip())
        else:
            raise ValueError("FlowInterrupt: укажите question или body")
        self.tool_call = tool_call
        self.flow_id = flow_id
        self.correlation_id = correlation_id
        super().__init__(interrupt_body_public_question(self.body))

    @property
    def question(self) -> str:
        return interrupt_body_public_question(self.body)


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
        state_snapshot: dict[str, Any],
        flow_id: str = "",
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.state_snapshot = state_snapshot
        self.flow_id = flow_id
        super().__init__(f"Breakpoint hit at node '{node_id}'")


class ToolExecutionError(Exception):
    """Ошибка выполнения tool."""

    def __init__(self, message: str, error: Exception | None = None):
        self.message = message
        self.error = error
        super().__init__(message)


class EdgeConditionError(Exception):
    """
    Сбой при вычислении условия исходящего ребра.
    Сохраняет индекс ребра для emit edge_error в UI.
    """

    def __init__(
        self,
        edge_index: int,
        from_node: str,
        to_node: str,
        original: Exception,
    ) -> None:
        self.edge_index = edge_index
        self.from_node = from_node
        self.to_node = to_node
        self.original = original
        super().__init__(str(original))
