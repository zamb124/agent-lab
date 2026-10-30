"""
Доступ к RAG namespace: HTTP-поиск через ``RagClient``, индексация через
``get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)``.
"""

from __future__ import annotations

from typing import override

from apps.flows.src.models.rag_resource_bind import RagResourceBindParams
from apps.flows.src.resources.index_profile_merge import merge_index_profile_dict_overlays
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.context import get_context
from core.namespace import NamespaceService
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.rag.models import RAGMetadata, RAGMetadataFilter, RAGSearchOptions
from core.rag.rag_http_namespace_search import merge_search_request_options
from core.types import JsonObject, require_json_object


class RAGResource:
    """
    Работа с RAG namespace.

    Пример:
        kb = RAGResource(
            "ns-1",
            namespace_service,
            search_options={
                "channels": {"semantic": True, "lexical": True},
                "rerank": True,
            },
        )
        results = await kb.search("Как оформить возврат?", top_k=3)
    """

    def __init__(
        self,
        namespace: str,
        namespace_service: NamespaceService,
        *,
        provider: str = RAG_IN_PROCESS_PROVIDER_ID,
        default_top_k: int = 5,
        company_id: str | None = None,
        search_options: RAGSearchOptions | None = None,
        filters: RAGMetadataFilter | None = None,
        index_profile_config: JsonObject | None = None,
        rag_client: RagClient | None = None,
    ) -> None:
        self._namespace_service: NamespaceService = namespace_service
        self._rag_client: RagClient = rag_client if rag_client is not None else RagClient()
        self._bind: RagResourceBindParams = RagResourceBindParams(
            namespace=namespace,
            provider=provider,
            default_top_k=default_top_k,
            company_id=company_id,
            search_options=search_options,
            filters=filters,
            index_profile_config=index_profile_config,
        )

    @property
    def namespace(self) -> str:
        return self._bind.namespace

    @property
    def provider(self) -> str:
        return self._bind.provider

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        filters: RAGMetadataFilter | None = None,
    ) -> list[JsonObject]:
        """Поиск по документам namespace через ``RagClient.search``."""
        limit = top_k if top_k is not None else self._bind.default_top_k
        merged_filters = dict(self._bind.filters) if self._bind.filters else {}
        if filters:
            merged_filters.update(filters)
        filter_arg: RAGMetadataFilter | None = merged_filters if merged_filters else None
        search_options = merge_search_request_options(self._bind.search_options, None)
        if search_options is None:
            search_options = RAGSearchOptions()

        data = await self._rag_client.search(
            namespace_id=self._bind.namespace,
            query=query,
            limit=limit,
            filters=filter_arg,
            provider=self._bind.provider,
            channels=search_options.channels,
            rrf_k=search_options.rrf_k,
            per_channel_top_k=search_options.per_channel_top_k,
            rerank=search_options.rerank,
            rerank_max_candidates=search_options.rerank_max_candidates,
            retrieval=search_options.retrieval,
            freshness_weight=search_options.freshness_weight,
            freshness_half_life_days=search_options.freshness_half_life_days,
        )

        raw_results = data.get("results")
        if raw_results is None:
            raise ServiceClientError('rag search: response has no results field')

        if not isinstance(raw_results, list):
            raise ServiceClientError('rag search: results must be an array')

        out: list[JsonObject] = []
        for item in raw_results:
            result = require_json_object(item, "rag search result")
            md = result.get("metadata")
            if md is None:
                md = {}
            elif not isinstance(md, dict):
                raise ServiceClientError('rag search: metadata must be an object')
            out.append(
                {
                    "content": result["content"],
                    "score": result["score"],
                    "document_id": result["document_id"],
                    "metadata": md,
                }
            )
        return out

    async def add_document(
        self,
        document_id: str,
        content: str,
        metadata: RAGMetadata | None = None,
        name: str | None = None,
        *,
        index_profile_config: JsonObject | None = None,
    ) -> JsonObject:
        """Загрузить текст документа в namespace."""
        context = get_context()
        if context is None or context.active_company is None:
            raise ValueError('RAGResource.add_document: context with active_company is required')
        _ = await self._namespace_service.get_or_create(
            self._bind.namespace,
            description=self._bind.namespace_description,
        )
        doc_metadata: RAGMetadata = dict(metadata) if metadata is not None else {}
        doc_metadata["document_id"] = document_id
        if self._bind.default_ttl_seconds is not None and "ttl_seconds" not in doc_metadata:
            doc_metadata["ttl_seconds"] = self._bind.default_ttl_seconds

        ipc_from_meta = doc_metadata.get("index_profile_config")
        if not isinstance(ipc_from_meta, dict):
            ipc_from_meta = None

        ipc = merge_index_profile_dict_overlays(
            self._bind.index_profile_config,
            ipc_from_meta,
            index_profile_config,
        )
        if ipc:
            doc_metadata["index_profile_config"] = ipc

        doc = await get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID).upload_document_from_text(
            namespace_id=self._bind.namespace,
            text=content,
            document_name=name or document_id,
            metadata=doc_metadata,
        )

        return {"document_id": doc.document_id, "status": "added"}

    @override
    def __repr__(self) -> str:
        return f"<RAGResource namespace={self._bind.namespace} provider={self._bind.provider}>"


__all__ = ["RAGResource"]
