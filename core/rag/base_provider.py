"""
Базовый абстрактный класс для всех RAG провайдеров.
Определяет единый интерфейс работы с векторными хранилищами.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from core.rag.models import RAGDocument, RAGSearchResult, RAGNamespace

logger = logging.getLogger(__name__)


class BaseRAGProvider(ABC):
    """
    Базовый абстрактный класс для всех RAG провайдеров.
    Определяет единый интерфейс для работы с RAG хранилищем.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Имя провайдера (agentset, pinecone, qdrant)"""
        pass
    
    @abstractmethod
    async def create_namespace(
        self,
        name: str,
        description: Optional[str] = None,
        **kwargs
    ) -> RAGNamespace:
        """Создает новый namespace для изоляции документов"""
        pass
    
    @abstractmethod
    async def get_namespace(self, namespace_id: str) -> Optional[RAGNamespace]:
        """Получает информацию о namespace"""
        pass
    
    @abstractmethod
    async def list_namespaces(self) -> List[RAGNamespace]:
        """Список всех namespaces"""
        pass
    
    @abstractmethod
    async def delete_namespace(self, namespace_id: str) -> bool:
        """Удаляет namespace и все его документы"""
        pass
    
    @abstractmethod
    async def upload_document_from_file(
        self,
        namespace_id: str,
        file_path: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает документ из файла.
        Провайдер сам обрабатывает парсинг, chunking, embedding.
        """
        pass
    
    @abstractmethod
    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает документ из S3.
        Провайдер скачивает из S3 и обрабатывает.
        """
        pass
    
    @abstractmethod
    async def upload_document_from_text(
        self,
        namespace_id: str,
        text: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает текст напрямую в RAG хранилище.
        """
        pass
    
    @abstractmethod
    async def get_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> Optional[RAGDocument]:
        """Получает информацию о документе"""
        pass
    
    @abstractmethod
    async def list_documents(
        self,
        namespace_id: str,
        limit: int = 100
    ) -> List[RAGDocument]:
        """Список документов в namespace"""
        pass
    
    @abstractmethod
    async def delete_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> bool:
        """Удаляет документ из namespace"""
        pass
    
    @abstractmethod
    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[RAGSearchResult]:
        """
        Семантический поиск по документам в namespace.
        """
        pass
    
    async def search_multiple_namespaces(
        self,
        namespace_ids: List[str],
        query: str,
        limit: int = 5,
        **kwargs
    ) -> Dict[str, List[RAGSearchResult]]:
        """
        Поиск сразу по нескольким namespace.
        Базовая реализация вызывает search() для каждого namespace.
        """
        results = {}
        for ns_id in namespace_ids:
            ns_results = await self.search(ns_id, query, limit, **kwargs)
            results[ns_id] = ns_results
            logger.debug(f"Поиск в {ns_id}: найдено {len(ns_results)} результатов")
        
        return results
    
    async def close(self):
        """Закрывает соединения"""
        pass
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

