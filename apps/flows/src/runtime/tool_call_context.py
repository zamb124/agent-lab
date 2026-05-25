"""ContextVar with the currently executing top-level LLM tool call."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.flows.src.streaming import BaseEmitter
    from core.state import ExecutionState


@dataclass(frozen=True)
class ActiveToolCallContext:
    """Runtime metadata for code running inside one tool invocation."""

    tool_name: str
    tool_call_id: str
    node_id: str
    state: "ExecutionState"
    emitter: "BaseEmitter | None" = None


_ACTIVE_TOOL_CALL_CONTEXT: ContextVar[ActiveToolCallContext | None] = ContextVar(
    "flows_active_tool_call_context",
    default=None,
)


def get_active_tool_call_context() -> ActiveToolCallContext | None:
    return _ACTIVE_TOOL_CALL_CONTEXT.get()


@contextmanager
def active_tool_call_context(
    *,
    tool_name: str,
    tool_call_id: str,
    node_id: str,
    state: "ExecutionState",
    emitter: "BaseEmitter | None" = None,
) -> Generator[ActiveToolCallContext, None, None]:
    ctx = ActiveToolCallContext(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        node_id=node_id,
        state=state,
        emitter=emitter,
    )
    token = _ACTIVE_TOOL_CALL_CONTEXT.set(ctx)
    try:
        yield ctx
    finally:
        _ACTIVE_TOOL_CALL_CONTEXT.reset(token)
