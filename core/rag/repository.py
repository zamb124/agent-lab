"""
RAG Repository: in-process ``BaseRAGProvider`` и опционально HTTP-поиск (контракт REST RAG API).

Дефолты ``namespace`` / ``provider`` / ``company_id`` / ``search_options`` / ``index_profile_config`` —
``RagResourceBindParams`` (как у ресурса ``rag`` в flows).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.clients.service_client import ServiceClient
from core.context import get_context
from core.logging import get_logger
from core.rag.base_provider import BaseRAGProvider
from core.rag.models import RAGDocument, RAGNamespace, RAGSearchResult
from core.rag.rag_http_namespace_search import (
    build_namespace_search_json_body,
    build_namespace_search_path,
    merge_search_request_options,
)
from core.rag.rag_resource_bind import RagResourceBindParams

logger = get_logger(__name__)
COMPANY_ID_HEADER = "X-Company-Id"


class RAGRepository:
    """
    Обертка над ``BaseRAGProvider``; опционально ``ServiceClient`` для ``search_namespace``
    (тот же контракт, что ``POST /rag/api/v1/namespaces/{id}/search``).
    """

    def __init__(
        self,
        provider: BaseRAGProvider,
        *,
        service_client: Optional[ServiceClient] = None,
        bind: Optional[RagResourceBindParams] = None,
    ) -> None:
        self._provider = provider
        self._service_client = service_client
        self._bind = bind

    @property
    def provider(self) -> BaseRAGProvider:
        return self._provider

    def _effective_bind(self, bind: Optional[RagResourceBindParams]) -> Optional[RagResourceBindParams]:
        return bind if bind is not None else self._bind

    def _merge_company_headers(
        self,
        company_id: Optional[str],
        bind: Optional[RagResourceBindParams],
    ) -> Optional[Dict[str, str]]:
        cid = company_id
        if cid is None and bind is not None:
            cid = bind.company_id
        if cid is not None:
            return {COMPANY_ID_HEADER: cid}
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError(
                "RAGRepository.search_namespace: нужен company_id (аргумент, bind или контекст с active_company)"
            )
        return {COMPANY_ID_HEADER: ctx.active_company.company_id}

    def _resolve_namespace_id(
        self,
        namespace_id: Optional[str],
        bind: Optional[RagResourceBindParams],
    ) -> str:
        ns = namespace_id
        if ns is None and bind is not None:
            ns = bind.namespace
        if not ns:
            raise ValueError(
                "RAGRepository: нужен namespace_id или bind.namespace (RagResourceBindParams)"
            )
        return ns

    def _require_service_client(self) -> ServiceClient:
        if self._service_client is None:
            raise ValueError(
                "RAGRepository.search_namespace: не задан service_client (нужен для HTTP-поиска)"
            )
        return self._service_client

    async def search_namespace(
        self,
        *,
        query: str,
        namespace_id: Optional[str] = None,
        limit: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        provider: Optional[str] = None,
        company_id: Optional[str] = None,
        search_options: Optional[Dict[str, Any]] = None,
        bind: Optional[RagResourceBindParams] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        ``POST /rag/api/v1/namespaces/{namespace_id}/search`` — тело как ``SearchRequest``.

        Дефолты и перекрытия полей — из ``bind`` / ``self._bind`` и явных аргументов.
        """
        client = self._require_service_client()
        b = self._effective_bind(bind)
        ns = self._resolve_namespace_id(namespace_id, b)

        lim = limit
        if lim is None:
            lim = b.default_top_k if b is not None else 5

        prov = provider
        if prov is None and b is not None:
            prov = b.provider

        merged_opts = merge_search_request_options(
            b.search_options if b is not None else None,
            search_options,
        )

        extra_headers = self._merge_company_headers(company_id, b)
        body = build_namespace_search_json_body(
            query=query,
            limit=lim,
            filters=filters,
            merged_search_options=merged_opts,
        )
        path = build_namespace_search_path(ns, provider=prov)

        kwargs: Dict[str, Any] = {"json": body, "timeout": timeout}
        if extra_headers is not None:
            kwargs["headers"] = extra_headers

        return await client.post("rag", path, **kwargs)

    async def list_documents(
        self,
        namespace_id: str,
        limit: int = 100,
    ) -> List[RAGDocument]:
        documents = await self.provider.list_documents(namespace_id, limit=limit)
        logger.info("Найдено %s документов в namespace %s", len(documents), namespace_id)
        return documents

    async def list_with_filters(
        self,
        namespace_id: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[RAGDocument]:
        documents = await self.provider.list_documents_with_filters(
            namespace_id=namespace_id,
            where=filters,
            limit=limit,
        )
        logger.info("Найдено %s документов с фильтрами в %s", len(documents), namespace_id)
        return documents

    async def get_document(
        self,
        namespace_id: str,
        document_id: str,
    ) -> Optional[RAGDocument]:
        return await self.provider.get_document(namespace_id, document_id)

    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RAGDocument:
        document = await self.provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=metadata or {},
        )
        logger.info("Документ %s загружен в namespace %s", document.document_id, namespace_id)
        return document

    async def upload_text(
        self,
        namespace_id: str,
        text: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RAGDocument:
        document = await self.provider.upload_document_from_text(
            namespace_id=namespace_id,
            text=text,
            document_name=document_name,
            metadata=metadata or {},
        )
        logger.info(
            "Текст загружен в namespace %s, document_id=%s",
            namespace_id,
            document.document_id,
        )
        return document

    async def delete_document(
        self,
        namespace_id: str,
        document_id: str,
    ) -> bool:
        success = await self.provider.delete_document(namespace_id, document_id)
        if success:
            logger.info("Документ %s удален из namespace %s", document_id, namespace_id)
        return success

    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[RAGSearchResult]:
        results = await self.provider.search(
            namespace_id=namespace_id,
            query=query,
            limit=limit,
            filters=filters,
            **kwargs,
        )
        logger.debug("Поиск '%s' в namespace %s: найдено %s результатов", query, namespace_id, len(results))
        return results

    async def search_multiple_namespaces(
        self,
        namespace_ids: List[str],
        query: str,
        limit: int = 5,
        **kwargs: Any,
    ) -> Dict[str, List[RAGSearchResult]]:
        return await self.provider.search_multiple_namespaces(
            namespace_ids=namespace_ids,
            query=query,
            limit=limit,
            **kwargs,
        )

    async def create_namespace(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> RAGNamespace:
        namespace = await self.provider.create_namespace(name, description)
        logger.info("Создан namespace: %s", namespace.namespace_id)
        return namespace

    async def get_namespace(self, namespace_id: str) -> Optional[RAGNamespace]:
        return await self.provider.get_namespace(namespace_id)

    async def list_namespaces(self) -> List[RAGNamespace]:
        return await self.provider.list_namespaces()

    async def delete_namespace(self, namespace_id: str) -> bool:
        success = await self.provider.delete_namespace(namespace_id)
        if success:
            logger.info("Namespace %s удален", namespace_id)
        return success
