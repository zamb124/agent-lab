"""Общий путь публикации pending UI events из ExecutionState."""

from __future__ import annotations

from typing import Any

from core.state import ExecutionState

from apps.flows.src.streaming.base import BaseEmitter

UI_EVENTS_KEY = "ui_events_pending"


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


async def emit_pending_ui_events(emitter: BaseEmitter, state: ExecutionState) -> None:
    raw_events = getattr(state, UI_EVENTS_KEY, None)
    if raw_events is None:
        return
    if not isinstance(raw_events, list):
        raise ValueError(f"state.{UI_EVENTS_KEY} must be a list")

    events = list(raw_events)
    setattr(state, UI_EVENTS_KEY, [])

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"state.{UI_EVENTS_KEY}[{index}] must be a dict")

        event_type = _require_non_empty_string(event.get("type"), f"state.{UI_EVENTS_KEY}[{index}].type")
        event_id = _require_non_empty_string(event.get("id"), f"state.{UI_EVENTS_KEY}[{index}].id")
        version = _require_non_empty_string(event.get("version"), f"state.{UI_EVENTS_KEY}[{index}].version")
        timestamp = _require_non_empty_string(event.get("timestamp"), f"state.{UI_EVENTS_KEY}[{index}].timestamp")
        source = _require_non_empty_string(event.get("source"), f"state.{UI_EVENTS_KEY}[{index}].source")

        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"state.{UI_EVENTS_KEY}[{index}].payload must be a dict")

        correlation_id_raw = event.get("correlation_id")
        correlation_id = (
            correlation_id_raw.strip()
            if isinstance(correlation_id_raw, str) and correlation_id_raw.strip()
            else None
        )

        await emitter.emit_ui_event(
            event_type=event_type,
            payload=payload,
            event_id=event_id,
            version=version,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
        )
