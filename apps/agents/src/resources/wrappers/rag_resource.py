"""
RAGResource - wrapper для rag ресурса.

Предоставляет доступ к семантическому поиску по документам.
Использует напрямую RAG провайдеры из core/rag.
"""

from typing import Any, Dict, List, Optional

from core.logging import get_logger

logger = get_logger(__name__)


class RAGResource:
    """
    Ресурс для работы с RAG namespace.
    
    Пример:
        results = await kb.search("Как оформить возврат?", top_k=3)
        for r in results:
            print(r.content, r.score)
    """
    
    def __init__(
        self,
        namespace: str,
        provider: str = "chromadb",
        default_top_k: int = 5,
        container: Any = None,
    ):
        self.namespace = namespace
        self.provider = provider
        self.default_top_k = default_top_k
        self._container = container
        self._rag_provider = None
    
    def _get_provider(self):
        """Получает RAG провайдер."""
        if self._rag_provider is None:
            from core.rag import get_default_rag_provider
            self._rag_provider = get_default_rag_provider()
        return self._rag_provider
    
    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Семантический поиск по документам.
        
        Args:
            query: Поисковый запрос
            top_k: Количество результатов
            filters: Фильтры метаданных
            
        Returns:
            Список результатов с полями: content, score, document_id, metadata
        """
        provider = self._get_provider()
        
        results = await provider.search(
            namespace_id=self.namespace,
            query=query,
            top_k=top_k or self.default_top_k,
            filters=filters,
        )
        
        # Преобразуем RAGSearchResult в dict
        return [
            {
                "content": r.content,
                "score": r.score,
                "document_id": r.document_id,
                "metadata": r.metadata,
            }
            for r in results
        ]
    
    async def add_document(
        self,
        document_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Добавить документ в namespace.
        
        Args:
            document_id: ID документа
            content: Текст документа
            metadata: Метаданные
            name: Имя документа (по умолчанию = document_id)
            
        Returns:
            Информация о добавленном документе
        """
        provider = self._get_provider()
        
        doc_metadata = metadata or {}
        doc_metadata["document_id"] = document_id
        
        doc = await provider.upload_document_from_text(
            namespace_id=self.namespace,
            text=content,
            document_name=name or document_id,
            metadata=doc_metadata,
        )
        
        return {"document_id": doc.document_id, "status": "added"}
    
    def __repr__(self) -> str:
        return f"<RAGResource namespace={self.namespace} provider={self.provider}>"
