"""Общий путь публикации pending UI events из ExecutionState."""

from __future__ import annotations

from apps.flows.src.streaming.base import BaseEmitter
from core.state import ExecutionState


async def emit_pending_ui_events(emitter: BaseEmitter, state: ExecutionState) -> None:
    events = list(state.ui_events_pending)
    state.ui_events_pending = []

    for event in events:
        await emitter.emit_ui_event(
            event_type=event.type,
            payload=event.payload,
            event_id=event.id,
            version=event.version,
            timestamp=event.timestamp,
            source=event.source,
            correlation_id=event.correlation_id,
        )
