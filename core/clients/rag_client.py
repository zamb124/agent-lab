"""
Типизированный клиент RAG API поверх ServiceClient (межсервисные вызовы, тулы flows).
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from core.clients.service_client import ServiceClient
from core.rag.rag_http_namespace_search import (
    RAG_API_V1_PREFIX,
    build_namespace_search_json_body,
    build_namespace_search_path,
    merge_search_request_options,
)


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
        description: Optional[str] = None,
        *,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        body: Dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        return await self._http.post(
            "rag",
            f"{RAG_API_V1_PREFIX}/namespaces",
            json=body,
            params=params or None,
        )

    async def ingest_text(
        self,
        namespace_id: str,
        text: str,
        *,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        document_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        body: Dict[str, Any] = {"text": text}
        if document_name is not None:
            body["document_name"] = document_name
        if metadata is not None:
            body["metadata"] = metadata
        if document_id is not None:
            body["document_id"] = document_id
        seg = quote(namespace_id, safe="")
        return await self._http.post(
            "rag",
            f"{RAG_API_V1_PREFIX}/namespaces/{seg}/ingest-text",
            json=body,
            params=params or None,
        )

    async def upload_namespace_document(
        self,
        namespace_id: str,
        *,
        filename: str,
        file_bytes: bytes,
        metadata: Dict[str, Any],
        content_type: str = "application/octet-stream",
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        seg = quote(namespace_id, safe="")
        path = f"{RAG_API_V1_PREFIX}/namespaces/{seg}/documents"
        params: Dict[str, str] | None = {"provider": provider} if provider is not None else None
        files = {"file": (filename, BytesIO(file_bytes), content_type)}
        return await self._http.post(
            "rag",
            path,
            files=files,
            data={"metadata": json.dumps(metadata)},
            params=params,
        )

    async def delete_namespace_document(
        self,
        namespace_id: str,
        document_id: str,
        *,
        provider: Optional[str] = None,
    ) -> Any:
        seg = quote(namespace_id, safe="")
        path = f"{RAG_API_V1_PREFIX}/namespaces/{seg}/documents/{document_id}"
        params: Dict[str, str] | None = {"provider": provider} if provider is not None else None
        return await self._http.delete("rag", path, params=params)

    async def get_document_processing_status(self, document_id: str) -> Dict[str, Any]:
        path = f"{RAG_API_V1_PREFIX}/documents/{document_id}/status"
        out = await self._http.get("rag", path)
        if not isinstance(out, dict):
            raise ValueError(f"RAG document status must be dict, got {type(out)}")
        return out

    def _pack_search_options(
        self,
        *,
        channels: Optional[Dict[str, Any]] = None,
        rrf_k: Optional[int] = None,
        per_channel_top_k: Optional[int] = None,
        rerank: Optional[bool] = None,
        retrieval: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        raw: Dict[str, Any] = {}
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
        filters: Optional[Dict[str, Any]] = None,
        provider: Optional[str] = None,
        channels: Optional[Dict[str, Any]] = None,
        rrf_k: Optional[int] = None,
        per_channel_top_k: Optional[int] = None,
        rerank: Optional[bool] = None,
        retrieval: Optional[bool] = None,
    ) -> Dict[str, Any]:
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
        return await self._http.post("rag", path, json=body)

    async def global_search(
        self,
        namespace_ids: List[str],
        query: str,
        *,
        limit: int = 5,
        provider: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        channels: Optional[Dict[str, Any]] = None,
        rrf_k: Optional[int] = None,
        per_channel_top_k: Optional[int] = None,
        rerank: Optional[bool] = None,
        retrieval: Optional[bool] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        body: Dict[str, Any] = {
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
        return await self._http.post(
            "rag",
            f"{RAG_API_V1_PREFIX}/search",
            json=body,
            params=params or None,
        )
