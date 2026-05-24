"""
Исключения агентов.
"""

from uuid import UUID

from core.clients.llm import LLMToolCall
from core.state.interrupt import (
    InterruptBody,
    UserMessageInterrupt,
    interrupt_body_public_question,
)
from core.types import JsonObject


class FlowInterrupt(Exception):
    """Прерывание выполнения с типизированным телом interrupt (HITL)."""

    def __init__(
        self,
        question: str | None = None,
        *,
        body: InterruptBody | None = None,
        tool_call: LLMToolCall | None = None,
        flow_id: str = "",
        correlation_id: UUID | None = None,
    ) -> None:
        if body is not None:
            if question is not None:
                raise ValueError("FlowInterrupt: нельзя передавать одновременно body и question")
            self.body: InterruptBody = body
        elif question is not None:
            if not question.strip():
                raise ValueError("FlowInterrupt: question должен быть непустой строкой")
            self.body = UserMessageInterrupt(question=question.strip())
        else:
            raise ValueError("FlowInterrupt: укажите question или body")
        self.tool_call: LLMToolCall | None = tool_call
        self.flow_id: str = flow_id
        self.correlation_id: UUID | None = correlation_id
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
        state_snapshot: JsonObject,
        flow_id: str = "",
    ) -> None:
        self.node_id: str = node_id
        self.node_type: str = node_type
        self.state_snapshot: JsonObject = state_snapshot
        self.flow_id: str = flow_id
        super().__init__(f"Breakpoint hit at node '{node_id}'")


class ToolExecutionError(Exception):
    """Ошибка выполнения tool."""

    def __init__(self, message: str, error: Exception | None = None) -> None:
        self.message: str = message
        self.error: Exception | None = error
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
        self.edge_index: int = edge_index
        self.from_node: str = from_node
        self.to_node: str = to_node
        self.original: Exception = original
        super().__init__(str(original))
