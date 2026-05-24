"""
RAG провайдер на базе Agentset.ai.

Документация: https://docs.agentset.ai/api-reference/introduction
"""

from pathlib import Path
from typing import cast as type_cast
from typing import override
from urllib.parse import unquote, urlparse

import httpx

from core.config import get_settings
from core.config.models import RAGProviderConfig
from core.http import ProxyStrategy, get_httpx_client
from core.http.client import SmartProxyClient
from core.logging import get_logger
from core.rag.models import (
    RAGDocument,
    RAGMetadata,
    RAGMetadataFilter,
    RAGNamespace,
    RAGSearchOptions,
    RAGSearchResult,
)
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.rag.upload_profile_binding import UploadProfileBinding
from core.types import JsonObject, JsonValue, require_json_object

# S3ClientFactory используется через базовый класс BaseRAGProvider
from core.utils.slug import generate_slug

from ..base_provider import BaseRAGProvider, validate_metadata_filters

logger = get_logger(__name__)


def _agentset_json_object(response: httpx.Response, field_name: str) -> JsonObject:
    return require_json_object(type_cast(JsonValue, response.json()), field_name)


class AgentsetRAGProvider(BaseRAGProvider):
    """RAG провайдер на базе Agentset.ai"""

    def __init__(self, config: RAGProviderConfig) -> None:
        super().__init__(config)

        api_key = config.api_key
        if not api_key:
            raise ValueError("api_key обязателен для Agentset провайдера")
        self.api_key: str = api_key

        self.base_url: str = (config.base_url or "https://api.agentset.ai").rstrip("/")
        self.timeout: int = config.timeout

        self._client: SmartProxyClient = get_httpx_client(
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
    @override
    def provider_name(self) -> str:
        return "agentset"

    @override
    async def close(self) -> None:
        await self._client.aclose()

    @override
    async def create_namespace(
        self,
        name: str,
        description: str | None = None,
    ) -> RAGNamespace:
        """
        Создает namespace в Agentset.
        Если не указать embeddingConfig - используется managed модель Agentset.

        Args:
            name: Имя namespace (используется как slug если slug не передан)
            description: Описание namespace
        """
        slug = generate_slug(name, add_hash=True)

        payload: JsonObject = {
            "name": name,
            "slug": slug
        }

        logger.info(f"Создание namespace: name='{name}', slug='{slug}'")

        try:
            response = await self._client.post("/v1/namespace", json=payload)
            _ = response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                logger.info(f"Namespace '{name}' уже существует (slug='{slug}'), получаем его")
                namespaces = await self.list_namespaces()
                for ns in namespaces:
                    agentset_data = ns.metadata.get("agentset_data")
                    if not isinstance(agentset_data, dict):
                        continue
                    ns_slug = agentset_data.get("slug")
                    if ns_slug == slug or ns.name == name:
                        logger.info(f"Найден существующий namespace: {name} (ID: {ns.namespace_id})")
                        return ns

                raise ValueError(
                    f"Namespace '{name}' уже существует, но не найден в списке. Попробуйте другое имя."
                )

            error_detail = ""
            try:
                error_body = _agentset_json_object(e.response, "agentset error response")
                error_detail = f" Детали: {error_body}"
            except Exception:
                error_detail = f" Тело ответа: {e.response.text[:500]}"

            raise httpx.HTTPStatusError(
                f"Ошибка создания namespace в AgentSet (name='{name}', slug='{slug}'): {e.response.status_code} - {e.response.reason_phrase}{error_detail}",
                request=e.request,
                response=e.response,
            ) from e

        result = _agentset_json_object(response, "agentset create namespace response")
        data_raw = result.get("data", result)
        data = require_json_object(data_raw, "agentset create namespace data")

        logger.info(f"Создан namespace: {name} (ID: {data.get('id')})")

        return RAGNamespace.model_validate(
            {
                "namespace_id": data["id"],
                "name": data["name"],
                "created_at": data.get("createdAt"),
                "metadata": {"agentset_data": data, "slug": data.get("slug")},
            }
        )

    @override
    async def get_namespace(self, namespace_id: str) -> RAGNamespace | None:
        """Получает namespace из Agentset"""
        response = await self._client.get(f"/v1/namespace/{namespace_id}")

        # Agentset возвращает 401 для чужих/несуществующих namespace (защита от перебора ID)
        if response.status_code in (404, 401):
            return None

        _ = response.raise_for_status()
        result = _agentset_json_object(response, "agentset get namespace response")
        data_raw = result.get("data", result)
        data = require_json_object(data_raw, "agentset get namespace data")

        return RAGNamespace.model_validate(
            {
                "namespace_id": data["id"],
                "name": data["name"],
                "document_count": data.get("documentCount", 0),
                "created_at": data.get("createdAt"),
                "metadata": {"agentset_data": data},
            }
        )

    @override
    async def list_namespaces(self) -> list[RAGNamespace]:
        """Список namespaces"""
        response = await self._client.get("/v1/namespace")
        _ = response.raise_for_status()

        result = _agentset_json_object(response, "agentset list namespaces response")
        items_raw = result.get("data")
        if not isinstance(items_raw, list):
            raise ValueError("agentset list namespaces data must be an array")
        items = [require_json_object(item, "agentset namespace item") for item in items_raw]

        return [
            RAGNamespace.model_validate(
                {
                    "namespace_id": item["id"],
                    "name": item["name"],
                    "document_count": item.get("documentCount", 0),
                    "created_at": item.get("createdAt"),
                    "metadata": {"agentset_data": item},
                }
            )
            for item in items
        ]

    @override
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

        _ = response.raise_for_status()
        logger.info(f"Удален namespace: {namespace_id}")
        return True

    async def _create_ingest_job_from_url(
        self,
        namespace_id: str,
        file_url: str,
        document_name: str,
        metadata: RAGMetadata | None
    ) -> JsonObject:
        """
        Создает ingest job из URL файла.

        Кодируем file_id в name для последующего восстановления:
        name = "{file_id}::{original_filename}"
        """
        file_id = metadata.get("file_id") if metadata else None

        if isinstance(file_id, str) and file_id:
            encoded_name = f"{file_id}::{document_name}"
        else:
            encoded_name = document_name

        payload: JsonObject = {
            "payload": {
                "type": "FILE",
                "fileUrl": file_url,
                "name": encoded_name
            }
        }

        if metadata:
            payload["config"] = {"metadata": metadata}

        response = await self._client.post(f"/v1/namespace/{namespace_id}/ingest-jobs", json=payload)
        _ = response.raise_for_status()

        result = _agentset_json_object(response, "agentset ingest job response")
        data_raw = result.get("data", result)
        data = require_json_object(data_raw, "agentset ingest job data")

        logger.info(f"Ingest job создан с именем: {encoded_name}")

        return data

    @override
    async def upload_document_from_file(
        self,
        namespace_id: str,
        file_path: str,
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
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
        doc_metadata = dict(metadata) if metadata is not None else {}
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name

        ingest_data = await self._create_ingest_job_from_url(
            namespace_id,
            file_url,
            doc_name,
            doc_metadata
        )

        logger.info(f"Документ '{doc_name}' загружен в namespace {namespace_id} через S3: {file_url}")

        return RAGDocument.model_validate(
            {
                "document_id": ingest_data["id"],
                "name": doc_name,
                "namespace": namespace_id,
                "status": ingest_data.get("status", "processing"),
                "metadata": doc_metadata,
                "created_at": ingest_data.get("createdAt"),
            }
        )

    @override
    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
        *,
        upload_profile: UploadProfileBinding | None = None,
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
            f"Документ '{doc_name}' загружен в namespace {namespace_id} через signed URL (срок индексации: 24ч, файл остается приватным)"
        )

        return RAGDocument.model_validate(
            {
                "document_id": ingest_data["id"],
                "name": doc_name,
                "namespace": namespace_id,
                "status": ingest_data.get("status", "processing"),
                "metadata": doc_metadata,
                "created_at": ingest_data.get("createdAt"),
            }
        )

    @override
    async def upload_document_from_text(
        self,
        namespace_id: str,
        text: str,
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
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
        )

    @override
    async def get_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> RAGDocument | None:
        """Получает информацию о документе"""
        response = await self._client.get(f"/v1/namespace/{namespace_id}/documents/{document_id}")

        # Agentset возвращает 401 для чужих/несуществующих ресурсов
        if response.status_code in (404, 401):
            return None

        _ = response.raise_for_status()
        result = _agentset_json_object(response, "agentset get document response")
        data_raw = result.get("data", result)
        data = require_json_object(data_raw, "agentset get document data")

        return RAGDocument.model_validate(
            {
                "document_id": data["id"],
                "name": data.get("name", ""),
                "namespace": namespace_id,
                "status": data.get("status", "unknown"),
                "metadata": require_json_object(
                    data.get("metadata", {}),
                    "agentset document metadata",
                ),
                "created_at": data.get("createdAt"),
            }
        )

    @override
    async def list_documents(
        self,
        namespace_id: str,
        limit: int = 100
    ) -> list[RAGDocument]:
        """Список документов в namespace"""
        response = await self._client.get(
            f"/v1/namespace/{namespace_id}/documents",
            params={"perPage": limit}
        )
        _ = response.raise_for_status()

        result = _agentset_json_object(response, "agentset list documents response")
        items_raw = result.get("data")
        if not isinstance(items_raw, list):
            raise ValueError("agentset list documents data must be an array")
        items = [require_json_object(item, "agentset document item") for item in items_raw]

        documents: list[RAGDocument] = []
        for item in items:
            ingest_job_id = item.get("ingestJobId")
            source = require_json_object(item.get("source", {}), "agentset document source")
            original_name: str | None = None
            file_id: str | None = None
            s3_key: str | None = None

            source_file_url = source.get("fileUrl")
            if isinstance(source_file_url, str) and source_file_url:
                # Парсим URL правильно: убираем query параметры и декодируем
                parsed_url = urlparse(source_file_url)
                original_name = unquote(Path(parsed_url.path).name)

            if isinstance(ingest_job_id, str) and ingest_job_id:
                job = await self._client.get(f"/v1/namespace/{namespace_id}/ingest-jobs/{ingest_job_id}")
                if job.status_code == 200:
                    job_response = _agentset_json_object(job, "agentset ingest job get response")
                    job_data = require_json_object(job_response.get("data", {}), "agentset ingest job get data")
                    job_payload = require_json_object(job_data.get("payload", {}), "agentset ingest job payload")
                    job_config = require_json_object(job_data.get("config", {}), "agentset ingest job config")
                    job_metadata = require_json_object(job_config.get("metadata", {}), "agentset ingest job metadata")
                    job_name_raw = job_payload.get("name", "")
                    job_name = job_name_raw if isinstance(job_name_raw, str) else ""

                    if "::" in job_name:
                        file_id, encoded_name = job_name.split("::", 1)
                        original_name = encoded_name or original_name
                    elif job_name:
                        original_name = job_name

                    # Извлекаем s3_key из metadata
                    s3_key_raw = job_metadata.get("s3_key")
                    if isinstance(s3_key_raw, str):
                        s3_key = s3_key_raw

            item_id = item.get("id")
            if not isinstance(item_id, str):
                raise ValueError("agentset document item.id must be a string")
            item_name = item.get("name")
            doc_name = original_name or (item_name if isinstance(item_name, str) and item_name else None) or f"document_{item_id[:8]}"

            # Генерируем signed URL если есть s3_key
            signed_url: str | None = None
            if s3_key:
                signed_url = await self._generate_signed_url(s3_key, expiration=3600)

            documents.append(
                RAGDocument.model_validate(
                    {
                        "document_id": item_id,
                        "name": doc_name,
                        "namespace": namespace_id,
                        "status": item.get("status", "unknown"),
                        "metadata": {
                            "file_id": file_id,
                            "s3_key": s3_key,
                            "signed_url": signed_url,
                        },
                        "created_at": item.get("createdAt"),
                    }
                )
            )

        return documents

    @override
    async def list_documents_with_filters(
        self,
        namespace_id: str,
        where: RAGMetadataFilter | None = None,
        limit: int = 100,
    ) -> list[RAGDocument]:
        if where:
            validate_metadata_filters(where)
            raise ValueError("AgentsetRAGProvider не поддерживает list_documents_with_filters")
        return await self.list_documents(namespace_id, limit=limit)

    @override
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

        _ = response.raise_for_status()
        logger.info(f"Удален документ: {document_id}")
        return True

    @override
    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: RAGMetadataFilter | None = None,
        search_options: RAGSearchOptions | None = None,
    ) -> list[RAGSearchResult]:
        """Семантический поиск в Agentset"""
        if search_options is not None and search_options.channels is not None and search_options.channels.lexical:
            raise ValueError("Лексический канал и гибридный поиск (RRF) поддерживаются только провайдером pgvector")

        payload: JsonObject = {
            "query": query,
            "topK": limit,
            "rerank": search_options.rerank if search_options is not None and search_options.rerank is not None else True,
            "includeMetadata": True
        }

        if filters:
            validate_metadata_filters(filters)
            payload["filter"] = filters

        response = await self._client.post(f"/v1/namespace/{namespace_id}/search", json=payload)
        _ = response.raise_for_status()

        result = _agentset_json_object(response, "agentset search response")
        results_raw = result.get("data")
        if not isinstance(results_raw, list):
            raise ValueError("agentset search data must be an array")
        results = [require_json_object(item, "agentset search item") for item in results_raw]

        logger.info(f"Поиск '{query}' в {namespace_id}: найдено {len(results)}")

        return [
            RAGSearchResult.model_validate(
                {
                    "content": item.get("text", ""),
                    "score": item.get("score", 0.0),
                    "document_id": item.get("id", ""),
                    "document_name": require_json_object(
                        item.get("metadata", {}),
                        "agentset search metadata",
                    ).get("filename", ""),
                    "metadata": require_json_object(
                        item.get("metadata", {}),
                        "agentset search metadata",
                    ),
                    "namespace": namespace_id,
                }
            )
            for item in results
        ]
