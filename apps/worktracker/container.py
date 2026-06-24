"""
WorktrackerContainer — DI контейнер сервиса ядра задач.

Наследует BaseContainer (user/company/namespace репозитории из shared БД) и
добавляет доступ к БД platform_worktracker, репозиторий, WorkItemService и
диспетчер хука завершения.
"""

from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger
from core.worktracker.db import WorktrackerDatabase
from core.worktracker.hook_dispatcher import ServiceClientHookDispatcher
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
    def hook_dispatcher(self) -> ServiceClientHookDispatcher:
        return ServiceClientHookDispatcher(service_client=self.service_client)

    @lazy
    def work_item_service(self) -> WorkItemService:
        return WorkItemService(
            repository=self.worktracker_repository,
            hook_dispatcher=self.hook_dispatcher,
        )


def _create_worktracker_container() -> WorktrackerContainer:
    settings = get_settings()
    if not settings.database.worktracker_url:
        raise ValueError("database.worktracker_url не задан")
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
get_container = _worktracker_registry.get
