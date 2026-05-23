"""
Контейнер зависимостей office.
"""


from apps.office.db.base import OfficeDatabase
from apps.office.db.repositories.catalog_repository import CatalogRepository
from apps.office.db.repositories.document_binding_repository import DocumentBindingRepository
from core.config import get_settings
from core.container import BaseContainer, lazy
from core.files.file_repository import FileRepository
from core.files.processors import FileProcessor
from core.logging import get_logger

logger = get_logger(__name__)
class OfficeContainer(BaseContainer):
    def __init__(self, db_url: str, shared_db_url: str | None = None) -> None:
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._office_db_url = db_url

    @lazy
    def office_db(self):
        return OfficeDatabase.get_instance(self._office_db_url)

    @lazy
    def document_binding_repository(self):
        return DocumentBindingRepository(db=self.office_db)

    @lazy
    def catalog_repository(self):
        return CatalogRepository(db=self.office_db)

    @lazy
    def file_repository(self):
        """
        Прямой доступ к storage (shared), без HTTPRepositoryProxy.

        FileRepository.owner_service == \"core\", а процесс называется documents — иначе
        get/set шли бы в core по HTTP. Эндпоинт office-download анонимный (Document Server),
        контекста с Bearer нет: прокси на get() давал бы 4xx/5xx и OnlyOffice видел 500.
        """
        return FileRepository(storage=self.shared_storage)

    @lazy
    def file_processor(self):
        return FileProcessor(file_repository=self.file_repository)

_office_container: OfficeContainer | None = None

def get_office_container() -> OfficeContainer:
    global _office_container
    if _office_container is None:
        settings = get_settings()
        if not settings.database.office_url:
            raise ValueError("database.office_url не задан")
        if not settings.database.shared_url:
            raise ValueError("database.shared_url не задан")
        _office_container = OfficeContainer(
            db_url=settings.database.office_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("OfficeContainer инициализирован")
    return _office_container

def set_office_container(container: OfficeContainer) -> None:
    global _office_container
    _office_container = container

def reset_office_container() -> None:
    global _office_container
    _office_container = None
    OfficeDatabase.reset()

get_container = get_office_container
