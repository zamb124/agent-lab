"""
Типизированный клиент RAG API поверх ServiceClient (межсервисные вызовы, тулы flows).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from core.clients.service_client import ServiceClient

_API_PREFIX = "/rag/api/v1"


class RagClient:
    """HTTP-клиент к сервису rag; контекст пользователя/компании — из заголовков ServiceClient."""

    def __init__(self, http: ServiceClient | None = None) -> None:
        self._http = http or ServiceClient()

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
            f"{_API_PREFIX}/namespaces",
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
            f"{_API_PREFIX}/namespaces/{seg}/ingest-text",
            json=body,
            params=params or None,
        )

    async def search(
        self,
        namespace_id: str,
        query: str,
        *,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        body: Dict[str, Any] = {"query": query, "limit": limit}
        if filters is not None:
            body["filters"] = filters
        seg = quote(namespace_id, safe="")
        return await self._http.post(
            "rag",
            f"{_API_PREFIX}/namespaces/{seg}/search",
            json=body,
            params=params or None,
        )

    async def global_search(
        self,
        namespace_ids: List[str],
        query: str,
        *,
        limit: int = 5,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if provider is not None:
            params["provider"] = provider
        return await self._http.post(
            "rag",
            f"{_API_PREFIX}/search",
            json={"namespace_ids": namespace_ids, "query": query, "limit": limit},
            params=params or None,
        )
