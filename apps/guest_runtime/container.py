"""DI контейнер фермы code_agent."""

from __future__ import annotations

from apps.guest_runtime.config import get_guest_runtime_settings
from apps.guest_runtime.db.repository import GuestRuntimeRepository
from apps.guest_runtime.services.farm_service import GuestFarmService
from apps.guest_runtime.services.lease_store import GuestLeaseStore
from core.clients.files_client import FilesClient
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class GuestRuntimeContainer(BaseContainer):
    """Composition root фермы guest_runtime."""

    @lazy
    def redis_client(self) -> RedisClient:
        redis_url = get_settings().database.redis_url
        if redis_url.strip() == "":
            raise ValueError("database.redis_url is required for guest_runtime")
        return RedisClient(redis_url)

    @lazy
    def guest_runtime_repository(self) -> GuestRuntimeRepository:
        return GuestRuntimeRepository(storage=self.storage)

    @lazy
    def lease_store(self) -> GuestLeaseStore:
        return GuestLeaseStore(self.redis_client, get_settings().guest_runtime)

    @lazy
    def files_client(self) -> FilesClient:
        return FilesClient(service="office")

    @lazy
    def farm_service(self) -> GuestFarmService:
        farm = get_settings().guest_runtime
        return GuestFarmService(
            repository=self.guest_runtime_repository,
            lease_store=self.lease_store,
            files_client=self.files_client,
            farm=farm,
        )


def _create_guest_runtime_container() -> GuestRuntimeContainer:
    settings = get_guest_runtime_settings()
    shared_url = settings.database.shared_url
    if shared_url is None or shared_url.strip() == "":
        raise ValueError("database.shared_url is required for guest_runtime")
    return GuestRuntimeContainer(
        db_url=shared_url,
        shared_db_url=shared_url,
    )


_guest_runtime_registry: ContainerRegistry[GuestRuntimeContainer] = ContainerRegistry(
    _create_guest_runtime_container, name="GuestRuntimeContainer"
)

get_guest_runtime_container = _guest_runtime_registry.get
reset_guest_runtime_container = _guest_runtime_registry.reset
