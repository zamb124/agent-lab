"""
Container - Dependency Injection контейнер.

Базовая реализация контейнера, которую расширяют сервисы.
"""

from core.container.base import BaseContainer, get_system_container, set_system_container, initialize_system_container

__all__ = [
    "BaseContainer",
    "get_system_container",
    "set_system_container",
    "initialize_system_container",
]

