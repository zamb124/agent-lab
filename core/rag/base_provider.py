"""
Базовый абстрактный класс для всех RAG провайдеров.
Определяет единый интерфейс работы с векторными хранилищами.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.rag.models import RAGDocument, RAGSearchResult, RAGNamespace
from core.files.s3_client import S3ClientFactory

logger = logging.getLogger(__name__)


# Общие content types для всех провайдеров
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".json": "application/json",
    ".xml": "application/xml",
    ".rtf": "application/rtf",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".epub": "application/epub+zip",
}


class BaseRAGProvider(ABC):
    """
    Базовый абстрактный класс для всех RAG провайдеров.
    Определяет единый интерфейс для работы с RAG хранилищем.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def _get_content_type(self, file_path: str) -> str:
        """Определяет content type по расширению файла"""
        suffix = Path(file_path).suffix.lower()
        return CONTENT_TYPES.get(suffix, "application/octet-stream")
    
    async def _upload_file_to_s3(
        self,
        file_path: str,
        namespace_id: str,
        public: bool = False,
    ) -> tuple[str, str, str, Optional[str]]:
        """
        Загружает файл в S3 и возвращает (s3_key, bucket_name, original_filename, public_url).
        
        Args:
            file_path: Путь к локальному файлу
            namespace_id: ID namespace для организации в S3
            public: Если True, файл загружается с public-read ACL и возвращается публичный URL
            
        Returns:
            (s3_key, bucket_name, original_filename, public_url или None)
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        s3_client = S3ClientFactory.create_default_client()
        if not s3_client:
            raise ValueError("S3 клиент не настроен для загрузки файлов в RAG")
        
        prefix = "rag_public" if public else "rag"
        s3_key = f"{prefix}/{namespace_id}/{uuid.uuid4().hex[:8]}_{path.name}"
        
        with open(file_path, "rb") as f:
            file_data = f.read()
        
        await s3_client.upload_bytes(
            data=file_data,
            key=s3_key,
            content_type=self._get_content_type(file_path),
            public=public,
        )
        
        public_url = None
        if public:
            public_url = f"{s3_client.endpoint_url}/{s3_client.bucket_name}/{s3_key}"
        
        logger.info(f"Файл загружен в S3: {s3_key} (public={public})")
        
        return s3_key, s3_client.bucket_name, path.name, public_url
    
    async def _download_file_from_s3(self, s3_key: str) -> tuple[bytes, str, str]:
        """
        Скачивает файл из S3 и возвращает (data, bucket_name, filename).
        
        Общая логика для всех провайдеров.
        """
        s3_client = S3ClientFactory.create_default_client()
        if not s3_client:
            raise ValueError("S3 клиент не настроен")
        
        file_data = await s3_client.download_bytes(s3_key)
        filename = Path(s3_key).name
        
        return file_data, s3_client.bucket_name, filename
    
    async def _generate_signed_url(self, s3_key: str, expiration: int = 3600) -> str:
        """
        Генерирует временный signed URL для доступа к файлу.
        
        Args:
            s3_key: Ключ файла в S3
            expiration: Время жизни URL в секундах (по умолчанию 1 час)
            
        Returns:
            Signed URL
        """
        s3_client = S3ClientFactory.create_default_client()
        if not s3_client:
            raise ValueError("S3 клиент не настроен")
        
        signed_url = await s3_client.generate_presigned_url(key=s3_key, expiration=expiration)
        if not signed_url:
            raise ValueError(f"Не удалось создать signed URL для файла: {s3_key}")
        
        return signed_url
    
    async def _upload_text_to_s3(
        self,
        text: str,
        namespace_id: str,
        filename: str,
    ) -> tuple[str, str]:
        """
        Загружает текст как файл в S3.
        
        Args:
            text: Текст для загрузки
            namespace_id: ID namespace
            filename: Имя файла (без расширения добавится .txt)
            
        Returns:
            (s3_key, bucket_name)
        """
        s3_client = S3ClientFactory.create_default_client()
        if not s3_client:
            raise ValueError("S3 клиент не настроен")
        
        safe_name = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).strip()
        if not safe_name:
            safe_name = "text"
        safe_name = safe_name[:40]
        
        s3_key = f"rag_text/{namespace_id}/{uuid.uuid4().hex[:8]}_{safe_name}.txt"
        
        await s3_client.upload_bytes(
            data=text.encode('utf-8'),
            key=s3_key,
            content_type="text/plain",
        )
        
        logger.info(f"Текст загружен в S3: {s3_key}")
        
        return s3_key, s3_client.bucket_name
    
    async def generate_download_url(
        self,
        namespace_id: str,
        document_id: str,
        expiration: int = 3600
    ) -> Optional[str]:
        """
        Генерирует временный URL для скачивания оригинала документа.
        
        Args:
            namespace_id: ID namespace
            document_id: ID документа
            expiration: Время жизни URL в секундах (по умолчанию 1 час)
            
        Returns:
            Signed URL или None если документ не найден
        """
        document = await self.get_document(namespace_id, document_id)
        if not document:
            return None
        
        s3_key = document.metadata.get("s3_key")
        if not s3_key:
            return None
        
        s3_client = S3ClientFactory.create_default_client()
        if not s3_client:
            return None
        
        return await s3_client.generate_presigned_url(key=s3_key, expiration=expiration)
    
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

