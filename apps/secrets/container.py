"""
SecretsContainer — DI контейнер сервиса версионируемых переменных.

Наследует BaseContainer и добавляет доступ к БД platform_secrets, репозиторий и
SecretsService.
"""

from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger
from core.secrets.db import SecretsDatabase
from core.secrets.repository import SecretsRepository
from core.secrets.service import SecretsService

logger = get_logger(__name__)


class SecretsContainer(BaseContainer):
    """Контейнер сервиса secrets."""

    def __init__(self, db_url: str, shared_db_url: str | None = None) -> None:
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._secrets_db_url: str = db_url

    @lazy
    def secrets_db(self) -> SecretsDatabase:
        return SecretsDatabase(self._secrets_db_url)

    @lazy
    def secrets_repository(self) -> SecretsRepository:
        return SecretsRepository(db=self.secrets_db)

    @lazy
    def secrets_service(self) -> SecretsService:
        return SecretsService(repository=self.secrets_repository)


def _create_secrets_container() -> SecretsContainer:
    settings = get_settings()
    if not settings.database.secrets_url:
        raise ValueError("database.secrets_url не задан")
    return SecretsContainer(
        db_url=settings.database.secrets_url,
        shared_db_url=settings.database.shared_url,
    )


_secrets_registry: ContainerRegistry[SecretsContainer] = ContainerRegistry(
    _create_secrets_container, name="SecretsContainer"
)

get_secrets_container = _secrets_registry.get
set_secrets_container = _secrets_registry.set
reset_secrets_container = _secrets_registry.reset
get_container = _secrets_registry.get
