"""
DI-контейнер provider_litserve.
"""

from __future__ import annotations

from core.config import get_settings
from core.container import BaseContainer
from core.logging import get_logger

logger = get_logger(__name__)
class ProviderLitserveContainer(BaseContainer):
    """Контейнер зависимостей для HTTP-обвязки provider_litserve."""

_provider_litserve_container: ProviderLitserveContainer | None = None

def get_provider_litserve_container() -> ProviderLitserveContainer:
    global _provider_litserve_container
    if _provider_litserve_container is None:
        settings = get_settings()
        if not settings.database.shared_url:
            raise ValueError("database.shared_url не задан")
        _provider_litserve_container = ProviderLitserveContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("ProviderLitserveContainer инициализирован")
    return _provider_litserve_container

def set_provider_litserve_container(container: ProviderLitserveContainer) -> None:
    global _provider_litserve_container
    _provider_litserve_container = container

def reset_provider_litserve_container() -> None:
    global _provider_litserve_container
    _provider_litserve_container = None

get_container = get_provider_litserve_container
