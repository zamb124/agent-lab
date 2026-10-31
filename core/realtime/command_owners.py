"""Владелец `op_*` по первому сегменту PlatformEvent.type.

Владелец есть только у сервиса с каталогом `<SVC>_OPERATIONS`
(`apps/<svc>/realtime/command_router.py`) — гейт `scripts/gates/backend/command_owner_catalogs.py`.
`frontend` — консоль компании (настройки, team, API-ключи, embed, billing,
админки system: platform_billing, platform_tracing, llm_model_scores, authz_explorer);
его анонимные и pre-session маршруты (публичный сайт, инвайты, webhooks)
остаются HTTP-протоколом без команд.
Протокольные сервисы (`voice`, `browser`, `guest_runtime`, `capability_gateway`,
`code_runner_*`, `realtime`) команд по шине не принимают: их API — собственный протокол
(WS-сессии, CDP, sandbox) и REST.
"""

from __future__ import annotations

_OWNER_BY_SCOPE: dict[str, str] = {
    "sync": "sync",
    "crm": "crm",
    "wiki": "wiki",
    "office": "office",
    "flows": "flows",
    "worktracker": "worktracker",
    "rag": "rag",
    "search": "search",
    "frontend": "frontend",
    "secrets": "secrets",
    "scheduler": "scheduler",
    "stock": "stock",
    "shop": "shop",
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
