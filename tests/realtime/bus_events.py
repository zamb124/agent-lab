"""Сборки PlatformEvent для E2E bus."""

from __future__ import annotations

from core.types import JsonObject


def bus_notify_event(
    *,
    event_id: str,
    user_id: str,
    title: str,
    company_id: str = "system",
) -> JsonObject:
    return {
        "event_id": event_id,
        "type": "notify/test/system_received",
        "company_id": company_id,
        "payload": {
            "title": title,
            "message": title,
            "kind": "system",
            "service": "test",
            "priority": "normal",
        },
        "meta": {"source": "system", "actor_user_id": user_id},
        "delivery": {"user_ids": [user_id]},
    }
