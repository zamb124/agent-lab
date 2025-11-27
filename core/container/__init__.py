"""
Container - Dependency Injection контейнер.

Базовая реализация контейнера, которую расширяют сервисы.
Сервисы используют свои контейнеры (get_agents_container, get_frontend_container).
Контейнер доступен через request.app.state.container.
"""

from core.container.base import BaseContainer

__all__ = [
    "BaseContainer",
]

