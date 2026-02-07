"""
RAG Repository - абстракция для работы с RAG namespace.

Предоставляет методы для работы с документами в любом namespace,
без привязки к конкретному flow или agent.
"""

import logging
from typing import List, Optional, Dict, Any

from core.rag.factory import get_default_rag_provider
from core.rag.models import RAGDocument, RAGSearchResult, RAGNamespace

logger = logging.getLogger(__name__)


class RAGRepository:
    """
    Репозиторий для работы с RAG документами.
    
    Обертка над BaseRAGProvider с упрощенным интерфейсом.
    Не привязан к flow - работает с namespace_id напрямую.
    """
    
    def __init__(self):
        self._provider = None
    
    @property
    def provider(self):
        """Lazy initialization RAG провайдера"""
        if self._provider is None:
            self._provider = get_default_rag_provider()
        return self._provider
    
    async def list_documents(
        self,
        namespace_id: str,
        limit: int = 100
    ) -> List[RAGDocument]:
        """
        Получает список документов в namespace.
        
        Args:
            namespace_id: ID namespace
            limit: Максимальное количество документов
            
        Returns:
            Список документов
        """
        documents = await self.provider.list_documents(namespace_id, limit=limit)
        logger.info(f"Найдено {len(documents)} документов в namespace {namespace_id}")
        return documents
    
    async def list_with_filters(
        self,
        namespace_id: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[RAGDocument]:
        """
        Получает документы с фильтрацией по metadata.
        
        Args:
            namespace_id: ID namespace
            filters: Фильтры для metadata (where clause)
            limit: Максимальное количество
            
        Returns:
            Список документов
        """
        documents = await self.provider.list_documents_with_filters(
            namespace_id=namespace_id,
            where=filters,
            limit=limit
        )
        logger.info(f"Найдено {len(documents)} документов с фильтрами в {namespace_id}")
        return documents
    
    async def get_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> Optional[RAGDocument]:
        """
        Получает документ по ID.
        
        Args:
            namespace_id: ID namespace
            document_id: ID документа
            
        Returns:
            Документ или None
        """
        return await self.provider.get_document(namespace_id, document_id)
    
    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RAGDocument:
        """
        Загружает документ из S3 в namespace.
        
        Args:
            namespace_id: ID namespace
            s3_key: Ключ файла в S3
            document_name: Имя документа
            metadata: Дополнительные метаданные
            
        Returns:
            Загруженный документ
        """
        document = await self.provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=metadata or {}
        )
        logger.info(f"Документ {document.document_id} загружен в namespace {namespace_id}")
        return document
    
    async def upload_text(
        self,
        namespace_id: str,
        text: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RAGDocument:
        """
        Загружает текст напрямую в namespace.
        
        Args:
            namespace_id: ID namespace
            text: Текст для загрузки
            document_name: Имя документа
            metadata: Дополнительные метаданные
            
        Returns:
            Загруженный документ
        """
        document = await self.provider.upload_document_from_text(
            namespace_id=namespace_id,
            text=text,
            document_name=document_name,
            metadata=metadata or {}
        )
        logger.info(f"Текст загружен в namespace {namespace_id}, document_id={document.document_id}")
        return document
    
    async def delete_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> bool:
        """
        Удаляет документ из namespace.
        
        Args:
            namespace_id: ID namespace
            document_id: ID документа
            
        Returns:
            True если удаление успешно
        """
        success = await self.provider.delete_document(namespace_id, document_id)
        if success:
            logger.info(f"Документ {document_id} удален из namespace {namespace_id}")
        return success
    
    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RAGSearchResult]:
        """
        Семантический поиск по документам в namespace.
        
        Args:
            namespace_id: ID namespace
            query: Поисковый запрос
            limit: Максимальное количество результатов
            filters: Фильтры метаданных
            
        Returns:
            Список результатов поиска
        """
        results = await self.provider.search(
            namespace_id=namespace_id,
            query=query,
            limit=limit,
            filters=filters
        )
        logger.debug(f"Поиск '{query}' в namespace {namespace_id}: найдено {len(results)} результатов")
        return results
    
    async def search_multiple_namespaces(
        self,
        namespace_ids: List[str],
        query: str,
        limit: int = 5
    ) -> Dict[str, List[RAGSearchResult]]:
        """
        Поиск по нескольким namespace.
        
        Args:
            namespace_ids: Список ID namespace
            query: Поисковый запрос
            limit: Максимальное количество результатов на namespace
            
        Returns:
            Словарь {namespace_id: [результаты]}
        """
        return await self.provider.search_multiple_namespaces(
            namespace_ids=namespace_ids,
            query=query,
            limit=limit
        )
    
    async def create_namespace(
        self,
        name: str,
        description: Optional[str] = None
    ) -> RAGNamespace:
        """
        Создает новый namespace.
        
        Args:
            name: Имя namespace
            description: Описание
            
        Returns:
            Созданный namespace
        """
        namespace = await self.provider.create_namespace(name, description)
        logger.info(f"Создан namespace: {namespace.namespace_id}")
        return namespace
    
    async def get_namespace(self, namespace_id: str) -> Optional[RAGNamespace]:
        """
        Получает информацию о namespace.
        
        Args:
            namespace_id: ID namespace
            
        Returns:
            Namespace или None
        """
        return await self.provider.get_namespace(namespace_id)
    
    async def list_namespaces(self) -> List[RAGNamespace]:
        """
        Получает список всех namespaces.
        
        Returns:
            Список namespaces
        """
        return await self.provider.list_namespaces()
    
    async def delete_namespace(self, namespace_id: str) -> bool:
        """
        Удаляет namespace и все его документы.
        
        Args:
            namespace_id: ID namespace
            
        Returns:
            True если удаление успешно
        """
        success = await self.provider.delete_namespace(namespace_id)
        if success:
            logger.info(f"Namespace {namespace_id} удален")
        return success









