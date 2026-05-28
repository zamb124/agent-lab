"""
Контейнер зависимостей office.
"""


from typing import override

from apps.office.db.base import OfficeDatabase
from apps.office.db.repositories.catalog_repository import CatalogRepository
from apps.office.db.repositories.document_binding_repository import DocumentBindingRepository
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.files.file_repository import FileRepository
from core.files.processors import FileProcessor
from core.logging import get_logger

logger = get_logger(__name__)
class OfficeContainer(BaseContainer):
    def __init__(self, db_url: str, shared_db_url: str | None = None) -> None:
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._office_db_url: str = db_url

    @lazy
    def office_db(self) -> OfficeDatabase:
        return OfficeDatabase.get_instance(self._office_db_url)

    @lazy
    def document_binding_repository(self) -> DocumentBindingRepository:
        return DocumentBindingRepository(db=self.office_db)

    @lazy
    def catalog_repository(self) -> CatalogRepository:
        return CatalogRepository(db=self.office_db)

    @lazy
    def redis_client(self) -> RedisClient:
        """
        Долгоживущий Redis-клиент сервиса: используется для распределённых блокировок
        (mutation lock на binding) и pub/sub-уведомлений о release.

        Один экземпляр на процесс — без RedisClient() на каждый HTTP-запрос,
        иначе по 1+ TCP-подключению на запрос и накопление полузакрытых сокетов.
        """
        redis_url = get_settings().database.redis_url
        return RedisClient(redis_url)

    @lazy
    @override
    def file_repository(self) -> FileRepository:
        """
        Прямой доступ к storage (shared), без HTTPRepositoryProxy.

        FileRepository.owner_service == \"core\", а процесс называется documents — иначе
        get/set шли бы в core по HTTP. Эндпоинт office-download анонимный (Document Server),
        контекста с Bearer нет: прокси на get() давал бы 4xx/5xx и OnlyOffice видел 500.
        """
        return FileRepository(storage=self.shared_storage)

    @lazy
    @override
    def file_processor(self) -> FileProcessor:
        return FileProcessor(file_repository=self.file_repository)

def _create_office_container() -> OfficeContainer:
    settings = get_settings()
    if not settings.database.office_url:
        raise ValueError("database.office_url не задан")
    if not settings.database.shared_url:
        raise ValueError("database.shared_url не задан")
    return OfficeContainer(
        db_url=settings.database.office_url,
        shared_db_url=settings.database.shared_url,
    )


_office_registry: ContainerRegistry[OfficeContainer] = ContainerRegistry(
    _create_office_container, name="OfficeContainer"
)

get_office_container = _office_registry.get
set_office_container = _office_registry.set


def reset_office_container() -> None:
    # Специфично для office: дополнительно сбрасываем singleton OfficeDatabase,
    # потому что её handle живёт в module-level кэше класса, а не внутри
    # контейнера. Это требование тестов, которые пересоздают БД.
    _office_registry.reset()
    OfficeDatabase.reset()


get_container = _office_registry.get
