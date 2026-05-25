"""
DI-контейнер provider_litserve.
"""

from __future__ import annotations

from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry
from core.logging import get_logger

logger = get_logger(__name__)


class ProviderLitserveContainer(BaseContainer):
    """Контейнер зависимостей для HTTP-обвязки provider_litserve."""


def _create_provider_litserve_container() -> ProviderLitserveContainer:
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url не задан")
    return ProviderLitserveContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_provider_litserve_registry: ContainerRegistry[ProviderLitserveContainer] = ContainerRegistry(
    _create_provider_litserve_container, name="ProviderLitserveContainer"
)

get_provider_litserve_container = _provider_litserve_registry.get
set_provider_litserve_container = _provider_litserve_registry.set
reset_provider_litserve_container = _provider_litserve_registry.reset
get_container = _provider_litserve_registry.get
