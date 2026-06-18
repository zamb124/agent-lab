"""
Типизированный клиент RAG API поверх ServiceClient (межсервисные вызовы, тулы flows).
"""

from __future__ import annotations

import json
from io import BytesIO
from urllib.parse import quote

from core.clients.service_client import ServiceClient
from core.rag.models import (
    RAGDocumentContent,
    RAGIngestTextResponse,
    RAGMetadata,
    RAGMetadataFilter,
    RAGSearchOptions,
)
from core.rag.rag_http_namespace_search import (
    RAG_API_V1_PREFIX,
    build_namespace_search_json_body,
    build_namespace_search_path,
    merge_search_request_options,
)
from core.rag_indexing_schema import SearchChannelsDefaults
from core.types import JsonObject, JsonValue, require_json_object


def _json_object_response(value: JsonValue, *, operation: str) -> JsonObject:
    return require_json_object(value, f"RAG {operation} response")


class RagClient:
    """HTTP-клиент к сервису rag; контекст пользователя/компании — из заголовков ServiceClient."""

    def __init__(self, http: ServiceClient | None = None) -> None:
        self._http: ServiceClient = http or ServiceClient()

    @staticmethod
    def files_download_url_path(document_id: str) -> str:
        """Относительный URL скачивания файла документа (как в ответах RAG API)."""
        return f"{RAG_API_V1_PREFIX}/files/download/{document_id}"

    async def create_namespace(
        self,
        name: str,
        description: str | None = None,
        *,
        provider: str | None = None,
    ) -> JsonObject:
        params: dict[str, str] = {}
        if provider is not None:
            params["provider"] = provider
        body: JsonObject = {"name": name}
        if description is not None:
            body["description"] = description
        return _json_object_response(
            await self._http.post(
                "rag",
                f"{RAG_API_V1_PREFIX}/namespaces",
                json=body,
                params=params or None,
            ),
            operation="create_namespace",
        )

    async def ingest_text(
        self,
        namespace_id: str,
        text: str,
        *,
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
        document_id: str | None = None,
        provider: str | None = None,
    ) -> RAGIngestTextResponse:
        params: dict[str, str] = {}
        if provider is not None:
            params["provider"] = provider
        body: JsonObject = {"text": text}
        if document_name is not None:
            body["document_name"] = document_name
        if metadata is not None:
            body["metadata"] = metadata
        if document_id is not None:
            body["document_id"] = document_id
        seg = quote(namespace_id, safe="")
        response = await self._http.post(
            "rag",
            f"{RAG_API_V1_PREFIX}/namespaces/{seg}/ingest-text",
            json=body,
            params=params or None,
        )
        return RAGIngestTextResponse.model_validate(
            _json_object_response(
                response,
                operation="ingest_text",
            )
        )

    async def upload_namespace_document(
        self,
        namespace_id: str,
        *,
        filename: str,
        file_bytes: bytes,
        metadata: RAGMetadata,
        content_type: str = "application/octet-stream",
        provider: str | None = None,
    ) -> JsonObject:
        seg = quote(namespace_id, safe="")
        path = f"{RAG_API_V1_PREFIX}/namespaces/{seg}/documents"
        params: dict[str, str] | None = {"provider": provider} if provider is not None else None
        files = {"file": (filename, BytesIO(file_bytes), content_type)}
        return _json_object_response(
            await self._http.post(
                "rag",
                path,
                files=files,
                data={"metadata": json.dumps(metadata)},
                params=params,
            ),
            operation="upload_namespace_document",
        )

    async def delete_namespace_document(
        self,
        namespace_id: str,
        document_id: str,
        *,
        provider: str | None = None,
    ) -> JsonValue:
        seg = quote(namespace_id, safe="")
        path = f"{RAG_API_V1_PREFIX}/namespaces/{seg}/documents/{document_id}"
        params: dict[str, str] | None = {"provider": provider} if provider is not None else None
        return await self._http.delete("rag", path, params=params)

    async def get_document_processing_status(self, document_id: str) -> JsonObject:
        path = f"{RAG_API_V1_PREFIX}/documents/{document_id}/status"
        out = await self._http.get("rag", path)
        return _json_object_response(out, operation="get_document_processing_status")

    async def get_namespace_document_content(
        self,
        namespace_id: str,
        document_id: str,
        *,
        provider: str | None = None,
    ) -> RAGDocumentContent:
        seg = quote(namespace_id, safe="")
        path = f"{RAG_API_V1_PREFIX}/namespaces/{seg}/documents/{quote(document_id, safe='')}/content"
        params: dict[str, str] | None = {"provider": provider} if provider is not None else None
        response = await self._http.get("rag", path, params=params)
        return RAGDocumentContent.model_validate(
            _json_object_response(response, operation="get_namespace_document_content")
        )

    def _pack_search_options(
        self,
        *,
        channels: SearchChannelsDefaults | dict[str, bool] | None = None,
        rrf_k: int | None = None,
        per_channel_top_k: int | None = None,
        rerank: bool | None = None,
        retrieval: bool | None = None,
    ) -> RAGSearchOptions | None:
        channels_model = (
            SearchChannelsDefaults.model_validate(channels)
            if channels is not None
            else None
        )
        raw = RAGSearchOptions(
            channels=channels_model,
            rrf_k=rrf_k,
            per_channel_top_k=per_channel_top_k,
            rerank=rerank,
            retrieval=retrieval,
        )
        return merge_search_request_options(None, raw)

    async def search(
        self,
        namespace_id: str,
        query: str,
        *,
        limit: int = 5,
        filters: RAGMetadataFilter | None = None,
        provider: str | None = None,
        channels: SearchChannelsDefaults | dict[str, bool] | None = None,
        rrf_k: int | None = None,
        per_channel_top_k: int | None = None,
        rerank: bool | None = None,
        retrieval: bool | None = None,
    ) -> JsonObject:
        merged_opts = self._pack_search_options(
            channels=channels,
            rrf_k=rrf_k,
            per_channel_top_k=per_channel_top_k,
            rerank=rerank,
            retrieval=retrieval,
        )
        body = build_namespace_search_json_body(
            query=query,
            limit=limit,
            filters=filters,
            merged_search_options=merged_opts,
        )
        path = build_namespace_search_path(namespace_id, provider=provider)
        return _json_object_response(
            await self._http.post("rag", path, json=body),
            operation="search",
        )

    async def global_search(
        self,
        namespace_ids: list[str],
        query: str,
        *,
        limit: int = 5,
        provider: str | None = None,
        filters: RAGMetadataFilter | None = None,
        channels: SearchChannelsDefaults | dict[str, bool] | None = None,
        rrf_k: int | None = None,
        per_channel_top_k: int | None = None,
        rerank: bool | None = None,
        retrieval: bool | None = None,
    ) -> JsonObject:
        params: dict[str, str] = {}
        if provider is not None:
            params["provider"] = provider
        body: JsonObject = {
            "namespace_ids": namespace_ids,
            "query": query,
            "limit": limit,
        }
        if filters is not None:
            body["filters"] = filters
        merged_opts = self._pack_search_options(
            channels=channels,
            rrf_k=rrf_k,
            per_channel_top_k=per_channel_top_k,
            rerank=rerank,
            retrieval=retrieval,
        )
        if merged_opts:
            body.update(merged_opts)
        return _json_object_response(
            await self._http.post(
                "rag",
                f"{RAG_API_V1_PREFIX}/search",
                json=body,
                params=params or None,
            ),
            operation="global_search",
        )
