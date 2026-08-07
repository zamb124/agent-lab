"""Publish already accepted Flow UI domain transitions through standard A2A artifacts."""

from __future__ import annotations

from apps.flows.src.streaming.base import BaseEmitter
from core.state import ExecutionState


async def emit_flow_ui_transitions(
    emitter: BaseEmitter,
    state: ExecutionState,
) -> None:
    for transition in state.drain_ui_transitions():
        await emitter.emit_flow_ui_transition(transition)


__all__ = ["emit_flow_ui_transitions"]
