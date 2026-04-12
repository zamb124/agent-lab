"""DI контейнер для RAG Service."""

from typing import Optional

from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class RAGContainer(BaseContainer):
    """DI контейнер сервиса RAG."""

    @lazy
    def document_status_repository(self):
        """Получает репозиторий статусов документов"""
        from core.db.repositories.document_status_repository import DocumentStatusRepository
        return DocumentStatusRepository(self.db_url)


_container: Optional[RAGContainer] = None


def get_rag_container() -> RAGContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _container
    if _container is None:
        from .config import get_rag_settings
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

