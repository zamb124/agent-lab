"""
FastAPI dependencies для Sync Service.
"""

from .container import SyncContainer, get_sync_container


def get_container_dep() -> SyncContainer:
    """Dependency для получения контейнера"""
    return get_sync_container()
