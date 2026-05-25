"""DI контейнер для RAG Service."""


from typing import override

from apps.rag.config import get_rag_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.db.repositories.document_status_repository import DocumentStatusRepository
from core.logging import get_logger
from core.rag.base_provider import BaseRAGProvider
from core.rag.factory import get_rag_provider

logger = get_logger(__name__)


class RAGContainer(BaseContainer):
    """DI контейнер сервиса RAG."""

    @lazy
    def document_status_repository(self) -> DocumentStatusRepository:
        """Получает репозиторий статусов документов"""
        return DocumentStatusRepository(self.required_db_url)

    @property
    @override
    def rag_provider(self) -> BaseRAGProvider:
        """Активный RAG-провайдер (``rag.default_provider``)."""
        settings = get_rag_settings()
        return get_rag_provider(settings=settings)


def _create_rag_container() -> RAGContainer:
    settings = get_rag_settings()
    return RAGContainer(
        db_url=settings.database.rag_url,
        shared_db_url=settings.database.shared_url,
    )


_rag_registry: ContainerRegistry[RAGContainer] = ContainerRegistry(
    _create_rag_container, name="RAGContainer"
)

get_rag_container = _rag_registry.get
set_rag_container = _rag_registry.set
reset_rag_container = _rag_registry.reset
