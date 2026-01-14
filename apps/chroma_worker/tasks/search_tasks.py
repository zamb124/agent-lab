"""
Tasks для семантического поиска в ChromaDB.
"""

from typing import Dict, Any, List, Optional
from apps.chroma_worker.chroma_broker import broker
from core.rag.factory import get_default_rag_provider
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task(queue_name="chroma")
async def search_task(
    namespace_id: str, 
    query: str, 
    limit: int = 5, 
    filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Семантический поиск в ChromaDB.
    
    Args:
        namespace_id: ID namespace в ChromaDB
        query: Поисковый запрос
        limit: Максимальное количество результатов
        filters: Фильтры для поиска
        
    Returns:
        Список результатов поиска
    """
    logger.info(f"ChromaWorker: поиск в namespace {namespace_id}, query='{query[:50]}'")
    
    provider = get_default_rag_provider()
    results = await provider.search(namespace_id, query, limit, filters)
    
    logger.info(f"ChromaWorker: найдено {len(results)} результатов")
    
    return [
        {
            "content": r.content,
            "score": r.score,
            "document_id": r.document_id,
            "document_name": r.document_name,
            "metadata": r.metadata
        }
        for r in results
    ]


@broker.task(queue_name="chroma")
async def query_raw_task(
    namespace_id: str,
    query_embeddings: Optional[List[List[float]]] = None,
    query_texts: Optional[List[str]] = None,
    n_results: int = 10,
    where: Optional[Dict[str, Any]] = None,
    where_document: Optional[Dict[str, Any]] = None,
    include: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Низкоуровневый запрос к ChromaDB.
    
    Args:
        namespace_id: ID namespace в ChromaDB
        query_embeddings: Векторы для поиска
        query_texts: Тексты для поиска (будут преобразованы в embeddings)
        n_results: Количество результатов
        where: Фильтры по metadata
        where_document: Фильтры по содержимому документа
        include: Какие поля включить в результат
        
    Returns:
        Сырые результаты от ChromaDB
    """
    logger.info(f"ChromaWorker: raw query в namespace {namespace_id}")
    
    provider = get_default_rag_provider()
    results = await provider.query_raw(
        namespace_id=namespace_id,
        query_embeddings=query_embeddings,
        query_texts=query_texts,
        n_results=n_results,
        where=where,
        where_document=where_document,
        include=include
    )
    
    return results

