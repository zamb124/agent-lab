"""Владелец `op_*` по первому сегменту PlatformEvent.type."""

from __future__ import annotations

_OWNER_BY_SCOPE: dict[str, str] = {
    "sync": "sync",
    "crm": "crm",
    "wiki": "wiki",
    "office": "office",
    "flows": "flows",
    "worktracker": "worktracker",
    "frontend": "frontend",
    "rag": "rag",
    "search": "search",
    "secrets": "secrets",
}


def owner_service_for_event_type(event_type: str) -> str:
    if not event_type:
        raise ValueError("event_type is required")
    scope = event_type.split("/", 1)[0]
    owner = _OWNER_BY_SCOPE.get(scope)
    if owner is None:
        raise ValueError(f"No command owner for event type {event_type!r}")
    return owner


def is_command_event_type(event_type: str) -> bool:
    return event_type.endswith("_requested")
