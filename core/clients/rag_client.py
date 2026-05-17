"""
Типизированный клиент RAG API поверх ServiceClient (межсервисные вызовы, тулы flows).
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from urllib.parse import quote

from core.clients.service_client import ServiceClient
from core.rag.rag_http_namespace_search import (
    RAG_API_V1_PREFIX,
    build_namespace_search_json_body,
    build_namespace_search_path,
    merge_search_request_options,
)


def _json_object_response(value: object, *, operation: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"RAG {operation} response must be dict, got {type(value).__name__}")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"RAG {operation} response contains non-string key")
        result[key] = item
    return result


class RagClient:
    """HTTP-клиент к сервису rag; контекст пользователя/компании — из заголовков ServiceClient."""

    def __init__(self, http: ServiceClient | None = None) -> None:
        self._http = http or ServiceClient()

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
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        body: dict[str, Any] = {"name": name}
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
        metadata: dict[str, Any] | None = None,
        document_id: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        body: dict[str, Any] = {"text": text}
        if document_name is not None:
            body["document_name"] = document_name
        if metadata is not None:
            body["metadata"] = metadata
        if document_id is not None:
            body["document_id"] = document_id
        seg = quote(namespace_id, safe="")
        return _json_object_response(
            await self._http.post(
                "rag",
                f"{RAG_API_V1_PREFIX}/namespaces/{seg}/ingest-text",
                json=body,
                params=params or None,
            ),
            operation="ingest_text",
        )

    async def upload_namespace_document(
        self,
        namespace_id: str,
        *,
        filename: str,
        file_bytes: bytes,
        metadata: dict[str, Any],
        content_type: str = "application/octet-stream",
        provider: str | None = None,
    ) -> dict[str, Any]:
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
    ) -> Any:
        seg = quote(namespace_id, safe="")
        path = f"{RAG_API_V1_PREFIX}/namespaces/{seg}/documents/{document_id}"
        params: dict[str, str] | None = {"provider": provider} if provider is not None else None
        return await self._http.delete("rag", path, params=params)

    async def get_document_processing_status(self, document_id: str) -> dict[str, Any]:
        path = f"{RAG_API_V1_PREFIX}/documents/{document_id}/status"
        out = await self._http.get("rag", path)
        return _json_object_response(out, operation="get_document_processing_status")

    def _pack_search_options(
        self,
        *,
        channels: dict[str, Any] | None = None,
        rrf_k: int | None = None,
        per_channel_top_k: int | None = None,
        rerank: bool | None = None,
        retrieval: bool | None = None,
    ) -> dict[str, Any] | None:
        raw: dict[str, Any] = {}
        if channels is not None:
            raw["channels"] = channels
        if rrf_k is not None:
            raw["rrf_k"] = rrf_k
        if per_channel_top_k is not None:
            raw["per_channel_top_k"] = per_channel_top_k
        if rerank is not None:
            raw["rerank"] = rerank
        if retrieval is not None:
            raw["retrieval"] = retrieval
        return merge_search_request_options(None, raw)

    async def search(
        self,
        namespace_id: str,
        query: str,
        *,
        limit: int = 5,
        filters: dict[str, Any] | None = None,
        provider: str | None = None,
        channels: dict[str, Any] | None = None,
        rrf_k: int | None = None,
        per_channel_top_k: int | None = None,
        rerank: bool | None = None,
        retrieval: bool | None = None,
    ) -> dict[str, Any]:
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
        filters: dict[str, Any] | None = None,
        channels: dict[str, Any] | None = None,
        rrf_k: int | None = None,
        per_channel_top_k: int | None = None,
        rerank: bool | None = None,
        retrieval: bool | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        body: dict[str, Any] = {
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
