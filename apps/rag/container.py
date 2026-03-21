"""DI контейнер для RAG Service."""

from typing import Optional

from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class RAGContainer(BaseContainer):
    """DI контейнер сервиса RAG."""

    @lazy
    def rag_provider(self):
        """Получает дефолтный RAG провайдер"""
        from core.rag.factory import get_default_rag_provider
        return get_default_rag_provider()

    @lazy
    def rag_repository(self):
        """Получает RAG репозиторий"""
        from core.rag.repository import RAGRepository
        return RAGRepository()

    @lazy
    def document_status_repository(self):
        """Получает репозиторий статусов документов"""
        from core.db.repositories.document_status_repository import DocumentStatusRepository
        return DocumentStatusRepository(self.db_url)
    
    async def get_s3_client(self):
        """Получает единый S3 клиент для работы с файлами"""
        from core.files.s3_client import get_default_s3_client
        return await get_default_s3_client()


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

