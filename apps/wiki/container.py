"""Контейнер зависимостей wiki."""

from apps.wiki.db.base import WikiDatabase
from apps.wiki.db.repositories.wiki_repository import WikiRepository
from apps.wiki.services.rag_index import WikiRagIndexService
from apps.wiki.services.wiki_service import WikiService
from core.clients.rag_client import RagClient
from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class WikiContainer(BaseContainer):
    """Контейнер сервиса wiki."""

    def __init__(self, db_url: str, shared_db_url: str | None = None) -> None:
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._wiki_db_url: str = db_url

    @lazy
    def wiki_db(self) -> WikiDatabase:
        return WikiDatabase(self._wiki_db_url)

    @lazy
    def wiki_repository(self) -> WikiRepository:
        return WikiRepository(db=self.wiki_db)

    @lazy
    def rag_client(self) -> RagClient:
        return RagClient()

    @lazy
    def wiki_rag_index_service(self) -> WikiRagIndexService:
        return WikiRagIndexService(rag_client=self.rag_client)

    @lazy
    def wiki_service(self) -> WikiService:
        return WikiService(
            repository=self.wiki_repository,
            rag_index=self.wiki_rag_index_service,
        )


def _create_wiki_container() -> WikiContainer:
    settings = get_settings()
    if not settings.database.wiki_url:
        raise ValueError("database.wiki_url не задан")
    if not settings.database.shared_url:
        raise ValueError("database.shared_url не задан")
    return WikiContainer(
        db_url=settings.database.wiki_url,
        shared_db_url=settings.database.shared_url,
    )


_wiki_registry: ContainerRegistry[WikiContainer] = ContainerRegistry(
    _create_wiki_container, name="WikiContainer"
)

get_wiki_container = _wiki_registry.get
set_wiki_container = _wiki_registry.set
reset_wiki_container = _wiki_registry.reset
get_container = _wiki_registry.get
