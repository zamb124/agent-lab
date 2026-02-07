"""
Tasks для семантического поиска через pgvector.
"""

from typing import Dict, Any, List, Optional

from apps.rag_worker.broker import broker
from core.rag.factory import get_default_rag_provider
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task(queue_name="rag")
async def search_task(
    namespace_id: str,
    query: str,
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Семантический поиск в vector_documents.

    Args:
        namespace_id: ID namespace
        query: Поисковый запрос
        limit: Максимальное количество результатов
        filters: Фильтры для поиска

    Returns:
        Список результатов поиска
    """
    logger.info(f"RAG Worker: поиск в namespace {namespace_id}, query='{query[:50]}'")

    provider = get_default_rag_provider()
    results = await provider.search(namespace_id, query, limit, filters)

    logger.info(f"RAG Worker: найдено {len(results)} результатов")

    return [
        {
            "content": r.content,
            "score": r.score,
            "document_id": r.document_id,
            "document_name": r.document_name,
            "metadata": r.metadata,
        }
        for r in results
    ]
