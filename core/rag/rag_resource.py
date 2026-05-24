"""
Доступ к RAG namespace из процессов с ``RAGRepository`` на контейнере
(``container.rag_repository``).

Поиск — ``RAGRepository.search_namespace`` с ``bind=self._bind``.
Загрузка текста — ``RAGRepository.provider.upload_document_from_text``.
"""

from __future__ import annotations

from typing import Protocol

from core.clients.service_client import ServiceClientError
from core.context import get_context
from core.db.repositories.namespace_repository import NamespaceRepository
from core.models.identity_models import Namespace
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.index_profile_merge import merge_index_profile_dict_overlays
from core.rag.models import RAGMetadata, RAGMetadataFilter, RAGSearchOptions
from core.rag.rag_resource_bind import RagResourceBindParams
from core.rag.repository import RAGRepository
from core.types import JsonObject, require_json_object


class _RAGResourceContainer(Protocol):
    rag_repository: RAGRepository
    namespace_repository: NamespaceRepository


class RAGResource:
    """
    Работа с RAG namespace.

    Пример:
        kb = RAGResource(
            "ns-1",
            container,
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
        container: _RAGResourceContainer,
        *,
        provider: str = RAG_IN_PROCESS_PROVIDER_ID,
        default_top_k: int = 5,
        company_id: str | None = None,
        search_options: RAGSearchOptions | None = None,
        filters: RAGMetadataFilter | None = None,
        index_profile_config: JsonObject | None = None,
    ) -> None:
        self._container: _RAGResourceContainer = container
        self._bind = RagResourceBindParams(
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
        """
        Поиск по документам namespace через ``RAGRepository.search_namespace``.
        """
        limit = top_k if top_k is not None else self._bind.default_top_k

        data = await self._container.rag_repository.search_namespace(
            query=query,
            limit=limit,
            filters=filters,
            bind=self._bind,
        )

        raw_results = data.get("results")
        if raw_results is None:
            raise ServiceClientError("rag search: в ответе нет поля results")

        if not isinstance(raw_results, list):
            raise ServiceClientError("rag search: results должен быть массивом")

        out: list[JsonObject] = []
        for item in raw_results:
            result = require_json_object(item, "rag search result")
            md = result.get("metadata")
            if md is None:
                md = {}
            elif not isinstance(md, dict):
                raise ServiceClientError("rag search: metadata должен быть объектом")
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
        repo = self._container.rag_repository
        context = get_context()
        if context is None or context.active_company is None:
            raise ValueError("RAGResource.add_document: контекст с active_company обязателен")
        namespace_repo = self._container.namespace_repository
        existing_namespace = await namespace_repo.get(self._bind.namespace)
        if existing_namespace is None:
            await namespace_repo.set(
                Namespace(name=self._bind.namespace, company_id=context.active_company.company_id)
            )
        doc_metadata = {**(metadata or {})}
        doc_metadata["document_id"] = document_id

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

        doc = await repo.provider.upload_document_from_text(
            namespace_id=self._bind.namespace,
            text=content,
            document_name=name or document_id,
            metadata=doc_metadata,
        )

        return {"document_id": doc.document_id, "status": "added"}

    def __repr__(self) -> str:
        return f"<RAGResource namespace={self._bind.namespace} provider={self._bind.provider}>"


__all__ = ["RAGResource"]
