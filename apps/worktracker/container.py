"""WorktrackerContainer — DI контейнер сервиса ядра задач."""

from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger
from core.worktracker.access_service import WorkQueueAccessService
from core.worktracker.db import WorktrackerDatabase
from core.worktracker.repository import WorktrackerRepository
from core.worktracker.service import WorkItemService

logger = get_logger(__name__)


class WorktrackerContainer(BaseContainer):
    """Контейнер сервиса worktracker."""

    def __init__(self, db_url: str, shared_db_url: str | None = None) -> None:
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._worktracker_db_url: str = db_url

    @lazy
    def worktracker_db(self) -> WorktrackerDatabase:
        return WorktrackerDatabase(self._worktracker_db_url)

    @lazy
    def worktracker_repository(self) -> WorktrackerRepository:
        return WorktrackerRepository(db=self.worktracker_db)

    @lazy
    def work_queue_access_service(self) -> WorkQueueAccessService:
        return WorkQueueAccessService(self.authz_service)

    @lazy
    def work_item_service(self) -> WorkItemService:
        return WorkItemService(
            repository=self.worktracker_repository,
            queue_access=self.work_queue_access_service,
            authz=self.authz_service,
        )


def _create_worktracker_container() -> WorktrackerContainer:
    settings = get_settings()
    if not settings.database.worktracker_url:
        raise ValueError("database.worktracker_url is not set")
    return WorktrackerContainer(
        db_url=settings.database.worktracker_url,
        shared_db_url=settings.database.shared_url,
    )


_worktracker_registry: ContainerRegistry[WorktrackerContainer] = ContainerRegistry(
    _create_worktracker_container, name="WorktrackerContainer"
)
get_worktracker_container = _worktracker_registry.get
set_worktracker_container = _worktracker_registry.set
reset_worktracker_container = _worktracker_registry.reset
