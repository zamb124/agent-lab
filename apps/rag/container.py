"""DI контейнер для RAG Service."""


from apps.rag.config import get_rag_settings
from core.container import BaseContainer, lazy
from core.db.repositories.document_status_repository import DocumentStatusRepository
from core.logging import get_logger
from core.rag.factory import get_rag_provider

logger = get_logger(__name__)


class RAGContainer(BaseContainer):
    """DI контейнер сервиса RAG."""

    @lazy
    def document_status_repository(self):
        """Получает репозиторий статусов документов"""
        return DocumentStatusRepository(self.required_db_url)

    @property
    def rag_provider(self):
        """Активный RAG-провайдер (``rag.default_provider``)."""
        settings = get_rag_settings()
        return get_rag_provider(settings=settings)


_container: RAGContainer | None = None


def get_rag_container() -> RAGContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _container
    if _container is None:
        settings = get_rag_settings()
        _container = RAGContainer(
            db_url=settings.database.rag_url,
            shared_db_url=settings.database.shared_url
        )
        logger.info("RAGContainer создан")
    return _container


def set_rag_container(container: RAGContainer) -> None:
    """Устанавливает контейнер (для тестов)"""
    global _container
    _container = container


def reset_rag_container() -> None:
    """Сбрасывает контейнер"""
    global _container
    _container = None
