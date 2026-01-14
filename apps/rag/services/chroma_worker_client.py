"""
Клиент для отправки задач в ChromaWorker через TaskIQ.

Этот клиент используется apps/rag для делегирования тяжелых операций
с ChromaDB (индексация, поиск) специализированному ChromaWorker.
"""

from typing import Dict, Any, List, Optional
from core.logging import get_logger
from apps.chroma_worker.tasks.indexing_tasks import upload_document_task, delete_document_task
from apps.chroma_worker.tasks.search_tasks import search_task
from apps.chroma_worker.tasks.maintenance_tasks import list_documents_task, cleanup_namespace_task

logger = get_logger(__name__)


class ChromaWorkerClient:
    """
    Клиент для отправки задач в ChromaWorker.
    
    ChromaWorker обрабатывает все операции с ChromaDB:
    - Индексация документов из S3
    - Семантический поиск
    - Удаление документов
    - Обслуживание namespace
    """
    
    async def upload_document(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Отправляет задачу индексации в ChromaWorker.
        
        Args:
            namespace_id: ID namespace в ChromaDB
            s3_key: Ключ файла в S3
            document_name: Имя документа
            metadata: Метаданные документа
            
        Returns:
            Информация о задаче с task_id
        """
        task = await upload_document_task.kiq(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=metadata
        )
        
        logger.info(f"RAG: отправлена задача индексации документа {document_name}, task_id={task.task_id}")
        
        return {
            "task_id": task.task_id,
            "status": "processing",
            "document_name": document_name
        }
    
    async def delete_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> Dict[str, Any]:
        """
        Отправляет задачу удаления документа в ChromaWorker.
        
        Args:
            namespace_id: ID namespace в ChromaDB
            document_id: ID документа для удаления
            
        Returns:
            Информация о задаче с task_id
        """
        task = await delete_document_task.kiq(
            namespace_id=namespace_id,
            document_id=document_id
        )
        
        logger.info(f"RAG: отправлена задача удаления документа {document_id}, task_id={task.task_id}")
        
        return {
            "task_id": task.task_id,
            "status": "processing",
            "document_id": document_id
        }
    
    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0
    ) -> List[Dict[str, Any]]:
        """
        Синхронный поиск через ChromaWorker с ожиданием результата.
        
        Args:
            namespace_id: ID namespace в ChromaDB
            query: Поисковый запрос
            limit: Максимальное количество результатов
            filters: Фильтры для поиска
            timeout: Таймаут ожидания результата в секундах
            
        Returns:
            Список результатов поиска
        """
        logger.info(f"RAG: поиск в namespace {namespace_id}, query='{query[:50]}'")
        
        # Отправляем задачу и ждем результата
        result = await search_task.kiq(
            namespace_id=namespace_id,
            query=query,
            limit=limit,
            filters=filters
        ).wait_result(timeout=timeout)
        
        logger.info(f"RAG: поиск завершен, найдено {len(result)} результатов")
        
        return result
    
    async def search_async(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Асинхронный поиск через ChromaWorker без ожидания результата.
        
        Args:
            namespace_id: ID namespace в ChromaDB
            query: Поисковый запрос
            limit: Максимальное количество результатов
            filters: Фильтры для поиска
            
        Returns:
            Информация о задаче с task_id
        """
        task = await search_task.kiq(
            namespace_id=namespace_id,
            query=query,
            limit=limit,
            filters=filters
        )
        
        logger.info(f"RAG: отправлена задача поиска, task_id={task.task_id}")
        
        return {
            "task_id": task.task_id,
            "status": "processing",
            "query": query
        }
    
    async def list_documents(
        self,
        namespace_id: str,
        timeout: float = 10.0
    ) -> List[Dict[str, Any]]:
        """
        Получить список всех документов в namespace.
        
        Args:
            namespace_id: ID namespace
            timeout: Таймаут ожидания результата
            
        Returns:
            Список документов с метаданными
        """
        result = await list_documents_task.kiq(
            namespace_id=namespace_id
        ).wait_result(timeout=timeout)
        
        return result
    
    async def cleanup_namespace(
        self,
        namespace_id: str
    ) -> Dict[str, Any]:
        """
        Отправляет задачу очистки namespace.
        
        Args:
            namespace_id: ID namespace для очистки
            
        Returns:
            Информация о задаче
        """
        task = await cleanup_namespace_task.kiq(
            namespace_id=namespace_id
        )
        
        logger.info(f"RAG: отправлена задача очистки namespace {namespace_id}, task_id={task.task_id}")
        
        return {
            "task_id": task.task_id,
            "status": "processing",
            "namespace": namespace_id
        }


