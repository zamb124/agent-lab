"""
RAG провайдер на базе Agentset.ai.

Документация: https://docs.agentset.ai/api-reference/introduction
"""

import httpx
import logging
import re
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, unquote

from ..base_provider import BaseRAGProvider
from core.rag.models import RAGDocument, RAGSearchResult, RAGNamespace
from core.http import get_proxy_url
from core.files.s3_client import S3ClientFactory
from core.utils.slug import generate_slug

logger = logging.getLogger(__name__)


class AgentsetRAGProvider(BaseRAGProvider):
    """RAG провайдер на базе Agentset.ai"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("api_key обязателен для Agentset провайдера")
        
        self.base_url = config.get("base_url", "https://api.agentset.ai").rstrip("/")
        self.timeout = config.get("timeout", 60)
        
        self.embedding_provider = config.get("embedding_provider", "openai")
        self.embedding_model = config.get("embedding_model", "text-embedding-3-small")
        self.embedding_api_key = config.get("embedding_api_key")
        
        proxy_url = get_proxy_url()
        
        if proxy_url:
            logger.info(f"🌐 Используем прокси для Agentset RAG: {proxy_url}")
        
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=self.timeout,
            proxy=proxy_url
        )
        
        logger.info(f"Agentset RAG провайдер инициализирован: {self.base_url}")
    
    @property
    def provider_name(self) -> str:
        return "agentset"
    
    async def close(self):
        await self._client.aclose()
    
    async def create_namespace(
        self,
        name: str,
        description: Optional[str] = None,
        **kwargs
    ) -> RAGNamespace:
        """
        Создает namespace в Agentset.
        Если не указать embeddingConfig - используется managed модель Agentset.
        
        Args:
            name: Имя namespace (используется как slug если slug не передан)
            description: Описание namespace
            **kwargs: Дополнительные параметры, включая slug
        """
        slug = kwargs.get("slug") or generate_slug(name, add_hash=True)
        
        payload = {
            "name": name,
            "slug": slug
        }
        
        logger.info(f"Создание namespace: name='{name}', slug='{slug}'")
        
        try:
            response = await self._client.post("/v1/namespace", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                logger.info(f"Namespace '{name}' уже существует (slug='{slug}'), получаем его")
                namespaces = await self.list_namespaces()
                for ns in namespaces:
                    ns_slug = ns.metadata.get("agentset_data", {}).get("slug")
                    if ns_slug == slug or ns.name == name:
                        logger.info(f"Найден существующий namespace: {name} (ID: {ns.namespace_id})")
                        return ns
                
                raise ValueError(
                    f"Namespace '{name}' уже существует, но не найден в списке. Попробуйте другое имя."
                )
            
            error_detail = ""
            try:
                error_body = e.response.json()
                error_detail = f" Детали: {error_body}"
            except Exception:
                error_detail = f" Тело ответа: {e.response.text[:500]}"
            
            raise httpx.HTTPStatusError(
                f"Ошибка создания namespace в AgentSet (name='{name}', slug='{slug}'): "
                f"{e.response.status_code} - {e.response.reason_phrase}{error_detail}",
                request=e.request,
                response=e.response,
            ) from e
        
        result = response.json()
        data = result.get("data", result)
        
        logger.info(f"Создан namespace: {name} (ID: {data.get('id')})")
        
        return RAGNamespace(
            namespace_id=data["id"],
            name=data["name"],
            created_at=data.get("createdAt"),
            metadata={"agentset_data": data, "slug": data.get("slug")}
        )
    
    async def get_namespace(self, namespace_id: str) -> Optional[RAGNamespace]:
        """Получает namespace из Agentset"""
        response = await self._client.get(f"/v1/namespace/{namespace_id}")
        
        if response.status_code == 404:
            return None
        
        response.raise_for_status()
        result = response.json()
        data = result.get("data", result)
        
        return RAGNamespace(
            namespace_id=data["id"],
            name=data["name"],
            document_count=data.get("documentCount", 0),
            created_at=data.get("createdAt"),
            metadata={"agentset_data": data}
        )
    
    async def list_namespaces(self) -> List[RAGNamespace]:
        """Список namespaces"""
        response = await self._client.get("/v1/namespace")
        response.raise_for_status()
        
        result = response.json()
        items = result.get("data", [])
        
        return [
            RAGNamespace(
                namespace_id=item["id"],
                name=item["name"],
                document_count=item.get("documentCount", 0),
                created_at=item.get("createdAt"),
                metadata={"agentset_data": item}
            )
            for item in items
        ]
    
    async def delete_namespace(self, namespace_id: str) -> bool:
        """Удаляет namespace"""
        response = await self._client.delete(f"/v1/namespace/{namespace_id}")
        
        if response.status_code == 404:
            return False
        
        response.raise_for_status()
        logger.info(f"Удален namespace: {namespace_id}")
        return True
    
    async def _create_ingest_job_from_url(
        self,
        namespace_id: str,
        file_url: str,
        document_name: str,
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Создает ingest job из URL файла.
        
        Кодируем file_id в name для последующего восстановления:
        name = "{file_id}::{original_filename}"
        """
        file_id = metadata.get("file_id") if metadata else None
        
        if file_id:
            encoded_name = f"{file_id}::{document_name}"
        else:
            encoded_name = document_name
        
        payload = {
            "payload": {
                "type": "FILE",
                "fileUrl": file_url,
                "name": encoded_name
            }
        }
        
        if metadata:
            payload["config"] = {"metadata": metadata}
        
        response = await self._client.post(f"/v1/namespace/{namespace_id}/ingest-jobs", json=payload)
        response.raise_for_status()
        
        result = response.json()
        data = result.get("data", result)
        
        logger.info(f"Ingest job создан с именем: {encoded_name}")
        
        return data
    
    def _get_content_type(self, file_path: str) -> str:
        """Определяет content type по расширению файла"""
        content_types = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".html": "text/html",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
        
        suffix = Path(file_path).suffix.lower()
        return content_types.get(suffix, "application/octet-stream")
    
    async def upload_document_from_file(
        self,
        namespace_id: str,
        file_path: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает документ из локального файла.
        
        Стратегия:
        1. Загружаем файл в S3 с публичным ACL
        2. Используем direct_s3_url для доступа
        3. Передаем URL в Agentset через fileUrl
        4. Agentset скачивает и обрабатывает
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        s3_client = S3ClientFactory.create_default_client()
        if not s3_client:
            raise ValueError("S3 клиент не настроен для загрузки файлов в RAG")
        
        s3_key = f"rag_public/{namespace_id}/{path.name}"
        
        with open(file_path, "rb") as f:
            file_data = f.read()
        
        await s3_client.upload_bytes(
            data=file_data,
            key=s3_key,
            content_type=self._get_content_type(file_path),
            acl="public-read"
        )
        
        file_url = f"{s3_client.endpoint_url}/{s3_client.bucket_name}/{s3_key}"
        
        doc_name = document_name or path.name
        
        ingest_data = await self._create_ingest_job_from_url(
            namespace_id,
            file_url,
            doc_name,
            metadata
        )
        
        logger.info(f"Документ '{doc_name}' загружен в namespace {namespace_id} через S3: {file_url}")
        
        return RAGDocument(
            document_id=ingest_data["id"],
            name=doc_name,
            namespace=namespace_id,
            status=ingest_data.get("status", "processing"),
            metadata=metadata or {},
            created_at=ingest_data.get("createdAt")
        )
    
    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает документ из S3 через signed URL.
        
        Стратегия:
        1. Генерируем signed URL на 24 часа для индексации Agentset
        2. Сохраняем оригинальный s3_key в metadata для генерации новых signed URL
        3. Передаем signed URL в Agentset (файл остается приватным в S3)
        4. После индексации URL протухнет, но документ уже в RAG
        """
        s3_client = S3ClientFactory.create_default_client()
        
        if not s3_client:
            raise ValueError("S3 клиент не настроен. Проверьте конфигурацию s3.enabled")
        
        # Генерируем signed URL на 24 часа (86400 сек) для индексации Agentset
        signed_url = await s3_client.generate_presigned_url(
            key=s3_key,
            expiration=86400  # 24 часа
        )
        
        if not signed_url:
            raise ValueError(f"Не удалось создать signed URL для файла: {s3_key}")
        
        doc_name = document_name or Path(s3_key).name
        
        # Сохраняем оригинальный s3_key для генерации новых signed URL
        if metadata is None:
            metadata = {}
        metadata["s3_key"] = s3_key
        
        ingest_data = await self._create_ingest_job_from_url(
            namespace_id,
            signed_url,  # Передаем signed URL вместо публичного
            doc_name,
            metadata
        )
        
        logger.info(
            f"Документ '{doc_name}' загружен в namespace {namespace_id} через signed URL "
            f"(срок индексации: 24ч, файл остается приватным)"
        )
        
        return RAGDocument(
            document_id=ingest_data["id"],
            name=doc_name,
            namespace=namespace_id,
            status=ingest_data.get("status", "processing"),
            metadata=metadata,
            created_at=ingest_data.get("createdAt")
        )

    async def upload_document_from_text(
        self,
        namespace_id: str,
        text: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает текст в Agentset, сначала сохраняя его как файл в S3.
        """
        doc_name = document_name or f"text_document_{len(text)}"

        # Сохраняем текст как файл в S3
        s3_client = S3ClientFactory.create_default_client()
        if not s3_client:
            raise ValueError("S3 клиент не настроен для загрузки текста в RAG")

        # Создаем временный файл в S3
        import uuid
        file_id_short = str(uuid.uuid4())[:8]  # Короткий UUID (8 символов)

        # Генерируем читаемое название файла
        if document_name and document_name.strip():
            # Если пользователь указал название - используем его, убираем расширение если есть
            base_name = document_name.strip()
            if '.' in base_name:
                base_name = base_name.rsplit('.', 1)[0]  # Убираем расширение

            safe_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_')).strip()
            if not safe_name:
                safe_name = "document"
            file_base_name = safe_name[:40]  # Ограничиваем длину
        else:
            # Если не указано - используем первые символы текста
            text_preview = text.strip()[:40].replace('\n', ' ').replace('\r', ' ')
            safe_name = "".join(c for c in text_preview if c.isalnum() or c in (' ', '-', '_')).strip()
            if not safe_name:
                safe_name = "text"
            file_base_name = safe_name

        s3_key = f"rag_text/{namespace_id}/{file_id_short}_{file_base_name}.txt"

        # Загружаем текст как bytes в S3
        text_bytes = text.encode('utf-8')
        await s3_client.upload_bytes(
            data=text_bytes,
            key=s3_key,
            content_type="text/plain",
            acl="private"  # Текст остается приватным в S3
        )

        # Обновляем метаданные с информацией о файле для правильного извлечения названия
        if metadata is None:
            metadata = {}
        metadata.update({
            "file_id": file_id_short,  # Добавляем короткий file_id для кодирования названия
            "original_text_length": len(text),
            "s3_key": s3_key,
            "uploaded_via": "text_upload"
        })

        # Используем существующий метод для загрузки из S3
        return await self.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=doc_name,
            metadata=metadata,
            **kwargs
        )
    
    async def get_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> Optional[RAGDocument]:
        """Получает информацию о документе"""
        response = await self._client.get(f"/v1/namespace/{namespace_id}/documents/{document_id}")
        
        if response.status_code == 404:
            return None
        
        response.raise_for_status()
        result = response.json()
        data = result.get("data", result)
        
        return RAGDocument(
            document_id=data["id"],
            name=data.get("name", ""),
            namespace=namespace_id,
            status=data.get("status", "unknown"),
            metadata=data.get("metadata", {}),
            created_at=data.get("createdAt")
        )
    
    async def list_documents(
        self,
        namespace_id: str,
        limit: int = 100
    ) -> List[RAGDocument]:
        """Список документов в namespace"""
        response = await self._client.get(
            f"/v1/namespace/{namespace_id}/documents",
            params={"perPage": limit}
        )
        response.raise_for_status()
        
        result = response.json()
        items = result.get("data", [])
        
        documents = []
        for item in items:
            ingest_job_id = item.get("ingestJobId")
            source = item.get("source", {})
            original_name = None
            file_id = None
            s3_key = None
            stored_metadata = item.get("metadata", {})

            if source.get("fileUrl"):
                # Парсим URL правильно: убираем query параметры и декодируем
                parsed_url = urlparse(source["fileUrl"])
                original_name = unquote(Path(parsed_url.path).name)

            if ingest_job_id:
                job = await self._client.get(f"/v1/namespace/{namespace_id}/ingest-jobs/{ingest_job_id}")
                if job.status_code == 200:
                    job_data = job.json().get("data", {})
                    job_name = job_data.get("payload", {}).get("name", "")
                    job_metadata = job_data.get("config", {}).get("metadata", {})

                    if "::" in job_name:
                        file_id, encoded_name = job_name.split("::", 1)
                        original_name = encoded_name or original_name
                    elif job_name:
                        original_name = job_name
                    
                    # Извлекаем s3_key из metadata
                    s3_key = job_metadata.get("s3_key")

            doc_name = original_name or item.get("name") or f"document_{item['id'][:8]}"

            # Генерируем signed URL если есть s3_key
            signed_url = None
            if s3_key:
                s3_client = S3ClientFactory.create_default_client()
                if s3_client:
                    signed_url = await s3_client.generate_presigned_url(
                        key=s3_key,
                        expiration=3600
                    )

            documents.append(RAGDocument(
                document_id=item["id"],
                name=doc_name,
                namespace=namespace_id,
                status=item.get("status", "unknown"),
                metadata={
                    "file_id": file_id,
                    "s3_key": s3_key,
                    "signed_url": signed_url  # Временная подписанная ссылка (1 час)
                },
                created_at=item.get("createdAt")
            ))
        
        return documents
    
    async def delete_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> bool:
        """Удаляет документ"""
        response = await self._client.delete(f"/v1/namespace/{namespace_id}/documents/{document_id}")
        
        if response.status_code == 404:
            return False
        
        response.raise_for_status()
        logger.info(f"Удален документ: {document_id}")
        return True
    
    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[RAGSearchResult]:
        """Семантический поиск в Agentset"""
        payload = {
            "query": query,
            "topK": limit,
            "rerank": kwargs.get("rerank", True),
            "includeMetadata": True
        }
        
        if filters:
            payload["filter"] = filters
        
        response = await self._client.post(f"/v1/namespace/{namespace_id}/search", json=payload)
        response.raise_for_status()
        
        result = response.json()
        results = result.get("data", [])
        
        logger.info(f"Поиск '{query}' в {namespace_id}: найдено {len(results)}")
        
        return [
            RAGSearchResult(
                content=item.get("text", ""),
                score=item.get("score", 0.0),
                document_id=item.get("id", ""),
                document_name=item.get("metadata", {}).get("filename", ""),
                metadata=item.get("metadata", {}),
                namespace=namespace_id
            )
            for item in results
        ]

