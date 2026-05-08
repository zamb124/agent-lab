"""
RAG Repository: in-process ``BaseRAGProvider`` и опционально HTTP-поиск (контракт REST RAG API),
постановка задач воркера через ``RagWorkerTasksPort``.

Дефолты ``namespace`` / ``provider`` / ``company_id`` / ``search_options`` / ``index_profile_config`` —
``RagResourceBindParams`` (как у ресурса ``rag`` в flows).
"""

from __future__ import annotations

from core.logging import get_logger
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

from core.clients.service_client import ServiceClient
from core.context import get_context
from core.rag.base_provider import BaseRAGProvider
from core.rag.index_profile_merge import merge_index_profile_dict_overlays
from core.rag.models import RAGDocument, RAGNamespace, RAGSearchResult
from core.rag.rag_resource_bind import RagResourceBindParams
from core.rag.rag_worker_tasks_port import RagWorkerTasksPort

logger = get_logger(__name__)
COMPANY_ID_HEADER = "X-Company-Id"
_SEARCH_REQUEST_OPTION_KEYS = frozenset({"channels", "rrf_k", "per_channel_top_k", "rerank"})

def _filter_search_options(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not raw:
        return {}
    return {k: v for k, v in raw.items() if k in _SEARCH_REQUEST_OPTION_KEYS}

def _merge_search_options(
    bind_opts: Optional[Dict[str, Any]],
    call_opts: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    merged: Dict[str, Any] = {}
    merged.update(_filter_search_options(bind_opts))
    merged.update(_filter_search_options(call_opts))
    return merged if merged else None

class RAGRepository:
    """
    Обертка над ``BaseRAGProvider``; опционально ``ServiceClient`` для ``search_namespace`` (тот же контракт,
    что ``POST /rag/api/v1/namespaces/{id}/search``) и ``RagWorkerTasksPort`` для постановки задач воркера.
    """

    def __init__(
        self,
        provider: BaseRAGProvider,
        *,
        service_client: Optional[ServiceClient] = None,
        bind: Optional[RagResourceBindParams] = None,
        worker_tasks: Optional[RagWorkerTasksPort] = None,
    ) -> None:
        self._provider = provider
        self._service_client = service_client
        self._bind = bind
        self._worker_tasks = worker_tasks

    @property
    def provider(self) -> BaseRAGProvider:
        return self._provider

    def _effective_bind(self, bind: Optional[RagResourceBindParams]) -> Optional[RagResourceBindParams]:
        return bind if bind is not None else self._bind

    def _require_active_company(self) -> str:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError(
                "RAGRepository: для операций воркера нужен контекст запроса с active_company"
            )
        return ctx.active_company.company_id

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

    def _require_worker_tasks(self) -> RagWorkerTasksPort:
        if self._worker_tasks is None:
            raise ValueError(
                "RAGRepository: для постановки задач воркера задайте worker_tasks (RagWorkerTasksPort)"
            )
        return self._worker_tasks

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

        merged_opts = _merge_search_options(
            b.search_options if b is not None else None,
            search_options,
        )

        extra_headers = self._merge_company_headers(company_id, b)
        body: Dict[str, Any] = {"query": query, "limit": lim}
        if filters is not None:
            body["filters"] = filters
        if merged_opts:
            body.update(merged_opts)

        ns_segment = quote(ns, safe="")
        path = f"/rag/api/v1/namespaces/{ns_segment}/search"
        if prov:
            path = f"{path}?{urlencode({'provider': prov})}"

        kwargs: Dict[str, Any] = {"json": body, "timeout": timeout}
        if extra_headers is not None:
            kwargs["headers"] = extra_headers

        return await client.post("rag", path, **kwargs)

    async def enqueue_s3_document_index(
        self,
        s3_key: str,
        document_name: str,
        metadata: Dict[str, Any],
        *,
        namespace_id: Optional[str] = None,
        bind: Optional[RagResourceBindParams] = None,
        index_profile_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Постановка индексации из S3 в очередь воркера; слияние ``index_profile_config`` как у ресурса ``rag``.
        """
        port = self._require_worker_tasks()
        b = self._effective_bind(bind)
        ns = self._resolve_namespace_id(namespace_id, b)
        company_id = self._require_active_company()

        meta = dict(metadata)
        ipc = merge_index_profile_dict_overlays(
            b.index_profile_config if b is not None else None,
            meta.get("index_profile_config") if isinstance(meta.get("index_profile_config"), dict) else None,
            index_profile_config,
        )
        if ipc:
            meta["index_profile_config"] = ipc

        return await port.enqueue_index_rag_document_s3(
            company_id=company_id,
            namespace_id=ns,
            s3_key=s3_key,
            document_name=document_name,
            metadata=meta,
        )

    async def enqueue_worker_delete_document(
        self,
        document_id: str,
        *,
        namespace_id: Optional[str] = None,
        bind: Optional[RagResourceBindParams] = None,
    ) -> Dict[str, Any]:
        """Постановка удаления документа через воркер (TaskIQ)."""
        port = self._require_worker_tasks()
        b = self._effective_bind(bind)
        ns = self._resolve_namespace_id(namespace_id, b)
        return await port.enqueue_delete_document(namespace_id=ns, document_id=document_id)

    async def list_documents_via_worker(
        self,
        *,
        namespace_id: Optional[str] = None,
        bind: Optional[RagResourceBindParams] = None,
        timeout: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """Список документов через задачу воркера с ожиданием результата."""
        port = self._require_worker_tasks()
        b = self._effective_bind(bind)
        ns = self._resolve_namespace_id(namespace_id, b)
        return await port.wait_list_documents(namespace_id=ns, timeout=timeout)

    async def enqueue_worker_cleanup_namespace(
        self,
        *,
        namespace_id: Optional[str] = None,
        bind: Optional[RagResourceBindParams] = None,
    ) -> Dict[str, Any]:
        """Постановка очистки namespace через воркер."""
        port = self._require_worker_tasks()
        b = self._effective_bind(bind)
        ns = self._resolve_namespace_id(namespace_id, b)
        return await port.enqueue_cleanup_namespace(namespace_id=ns)

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
