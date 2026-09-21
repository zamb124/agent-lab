"""Контейнер realtime bus."""

from apps.realtime.db.base import RealtimeDatabase
from apps.realtime.db.repository import PlatformEventLogRepository
from apps.realtime.services.bus_service import RealtimeBusService
from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy


class RealtimeContainer(BaseContainer):
    def __init__(self, db_url: str, shared_db_url: str | None = None) -> None:
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._realtime_db_url: str = db_url

    @lazy
    def realtime_db(self) -> RealtimeDatabase:
        return RealtimeDatabase(self._realtime_db_url)

    @lazy
    def event_log_repository(self) -> PlatformEventLogRepository:
        return PlatformEventLogRepository(db=self.realtime_db)

    @lazy
    def bus_service(self) -> RealtimeBusService:
        return RealtimeBusService(repository=self.event_log_repository)


def _create_realtime_container() -> RealtimeContainer:
    settings = get_settings()
    if not settings.database.realtime_url:
        raise ValueError("database.realtime_url is not set")
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is not set")
    return RealtimeContainer(
        db_url=settings.database.realtime_url,
        shared_db_url=settings.database.shared_url,
    )


_realtime_registry: ContainerRegistry[RealtimeContainer] = ContainerRegistry(
    _create_realtime_container, name="RealtimeContainer"
)

get_realtime_container = _realtime_registry.get
set_realtime_container = _realtime_registry.set
reset_realtime_container = _realtime_registry.reset
get_container = _realtime_registry.get
