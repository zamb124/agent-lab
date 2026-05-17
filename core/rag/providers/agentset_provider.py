"""
RAG провайдер на базе Agentset.ai.

Документация: https://docs.agentset.ai/api-reference/introduction
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

import httpx

from core.config import get_settings
from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.rag.models import RAGDocument, RAGNamespace, RAGSearchResult
from core.rag.ttl import ensure_ttl_seconds_in_metadata

# S3ClientFactory используется через базовый класс BaseRAGProvider
from core.utils.slug import generate_slug

from ..base_provider import BaseRAGProvider, validate_metadata_filters

logger = get_logger(__name__)
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

        self._client = get_httpx_client(
            timeout=self.timeout,
            strategy=ProxyStrategy.SMART,
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
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

        payload: dict[str, Any] = {
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

        # Agentset возвращает 401 для чужих/несуществующих namespace (защита от перебора ID)
        if response.status_code in (404, 401):
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

        # Agentset возвращает 401 для чужих/несуществующих namespace
        if response.status_code in (404, 401):
            return False

        # 422/500 - баг Agentset с полем createdAt (expected date, received string)
        if response.status_code in (422, 500):
            logger.warning(f"Не удалось удалить namespace {namespace_id}: {response.text}")
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

        payload: dict[str, Any] = {
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
        1. Загружаем файл в S3 с публичным ACL (через базовый метод)
        2. Передаем публичный URL в Agentset через fileUrl
        3. Agentset скачивает и обрабатывает
        """
        s3_key, bucket_name, original_filename = await self._upload_file_to_s3(
            file_path, namespace_id, public=False
        )
        file_url = await self._generate_signed_url(s3_key)

        doc_name = document_name or original_filename

        # Сохраняем s3_key в metadata для доступа к оригиналу
        doc_metadata = metadata or {}
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name

        ingest_data = await self._create_ingest_job_from_url(
            namespace_id,
            file_url,
            doc_name,
            doc_metadata
        )

        logger.info(f"Документ '{doc_name}' загружен в namespace {namespace_id} через S3: {file_url}")

        return RAGDocument(
            document_id=ingest_data["id"],
            name=doc_name,
            namespace=namespace_id,
            status=ingest_data.get("status", "processing"),
            metadata=doc_metadata,
            created_at=ingest_data.get("createdAt")
        )

    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        upload_profile: Optional[object] = None,
        **kwargs,
    ) -> RAGDocument:
        """
        Загружает документ из S3 через signed URL.

        Стратегия:
        1. Генерируем signed URL на 24 часа для индексации Agentset
        2. Сохраняем оригинальный s3_key в metadata для генерации новых signed URL
        3. Передаем signed URL в Agentset (файл остается приватным в S3)
        4. После индексации URL протухнет, но документ уже в RAG
        """
        if upload_profile is not None:
            raise ValueError("upload_profile поддерживается только провайдером pgvector")

        # Генерируем signed URL на 24 часа для индексации Agentset
        signed_url = await self._generate_signed_url(s3_key, expiration=86400)

        doc_name = document_name or Path(s3_key).name

        # Сохраняем оригинальный s3_key для генерации новых signed URL
        doc_metadata = ensure_ttl_seconds_in_metadata(
            dict(metadata or {}),
            default_ttl_seconds=get_settings().rag.ttl.default_ttl_seconds,
        )
        doc_metadata["s3_key"] = s3_key

        ingest_data = await self._create_ingest_job_from_url(
            namespace_id,
            signed_url,
            doc_name,
            doc_metadata
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
            metadata=doc_metadata,
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
        # Генерируем имя файла
        if document_name and document_name.strip():
            base_name = document_name.strip()
            if '.' in base_name:
                base_name = base_name.rsplit('.', 1)[0]
            filename = base_name
        else:
            text_preview = text.strip()[:40].replace('\n', ' ').replace('\r', ' ')
            filename = text_preview or "text"

        doc_name = document_name or f"text_document_{len(text)}"

        # Загружаем текст в S3 через базовый метод
        s3_key, bucket_name = await self._upload_text_to_s3(text, namespace_id, filename)

        # Обновляем метаданные (канонический ``ttl_seconds`` для политики retention)
        doc_metadata = ensure_ttl_seconds_in_metadata(
            dict(metadata or {}),
            default_ttl_seconds=get_settings().rag.ttl.default_ttl_seconds,
        )
        doc_metadata.update({
            "original_text_length": len(text),
            "s3_key": s3_key,
            "s3_bucket": bucket_name,
            "uploaded_via": "text_upload"
        })

        # Используем существующий метод для загрузки из S3
        return await self.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=doc_name,
            metadata=doc_metadata,
            **kwargs
        )

    async def get_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> Optional[RAGDocument]:
        """Получает информацию о документе"""
        response = await self._client.get(f"/v1/namespace/{namespace_id}/documents/{document_id}")

        # Agentset возвращает 401 для чужих/несуществующих ресурсов
        if response.status_code in (404, 401):
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
            item.get("metadata", {})

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
                try:
                    signed_url = await self._generate_signed_url(s3_key, expiration=3600)
                except ValueError:
                    pass  # S3 не настроен

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

    async def list_documents_with_filters(
        self,
        namespace_id: str,
        where: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[RAGDocument]:
        if where:
            validate_metadata_filters(where)
            raise ValueError("AgentsetRAGProvider не поддерживает list_documents_with_filters")
        return await self.list_documents(namespace_id, limit=limit)

    async def delete_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> bool:
        """Удаляет документ"""
        response = await self._client.delete(f"/v1/namespace/{namespace_id}/documents/{document_id}")

        # Agentset возвращает 401 для чужих/несуществующих ресурсов
        if response.status_code in (404, 401):
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
        ch = kwargs.get("channels")
        if isinstance(ch, dict) and bool(ch.get("lexical", False)):
            raise ValueError("Лексический канал и гибридный поиск (RRF) поддерживаются только провайдером pgvector")

        payload = {
            "query": query,
            "topK": limit,
            "rerank": kwargs.get("rerank", True),
            "includeMetadata": True
        }

        if filters:
            validate_metadata_filters(filters)
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
