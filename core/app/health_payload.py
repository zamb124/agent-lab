"""
Общий JSON для эндпоинтов health (в т.ч. алиас под публичным URL-префиксом сервиса).
"""

from __future__ import annotations

from core.config.base import BaseSettings


def build_health_payload(settings: BaseSettings) -> dict[str, str]:
    payload: dict[str, str] = {
        "status": "healthy",
        "service": settings.server.name,
    }
    dep = settings.server.deployment_version
    if dep:
        payload["deployment_version"] = dep
    return payload
