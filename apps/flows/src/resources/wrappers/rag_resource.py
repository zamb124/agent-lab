"""
RAGResource - wrapper для rag ресурса.

``RAGRepository`` — ``container.rag_repository`` из ``BaseContainer`` (in-process провайдер — ``pgvector``,
``service_client`` для HTTP-поиска).

Поиск — ``RAGRepository.search_namespace`` (``ServiceClient`` → REST RAG API) с ``bind=self._bind``.

Загрузка текста — in-process ``RAGRepository.provider.upload_document_from_text`` с тем же ``index_profile_config``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.clients.service_client import ServiceClientError
from core.rag.index_profile_merge import merge_index_profile_dict_overlays
from core.rag.rag_resource_bind import RagResourceBindParams


class RAGResource:
    """
    Ресурс для работы с RAG namespace.

    Пример:
        kb = RAGResource(
            "ns-1",
            get_container(),
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
        container: Any,
        *,
        provider: str = "pgvector",
        default_top_k: int = 5,
        company_id: Optional[str] = None,
        search_options: Optional[Dict[str, Any]] = None,
        index_profile_config: Optional[Dict[str, Any]] = None,
    ):
        self._container = container
        self._bind = RagResourceBindParams(
            namespace=namespace,
            provider=provider,
            default_top_k=default_top_k,
            company_id=company_id,
            search_options=search_options,
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
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Поиск по документам namespace через ``RAGRepository.search_namespace`` (дефолты из ``RagResourceBindParams``).
        """
        limit = top_k if top_k is not None else self._bind.default_top_k

        data = await self._container.rag_repository.search_namespace(
            query=query,
            limit=limit,
            filters=filters,
            bind=self._bind,
        )

        if not isinstance(data, dict):
            raise ServiceClientError("rag search: ожидался JSON-объект")
        raw_results = data.get("results")
        if raw_results is None:
            raise ServiceClientError("rag search: в ответе нет поля results")

        out: List[Dict[str, Any]] = []
        for item in raw_results:
            if not isinstance(item, dict):
                raise ServiceClientError("rag search: элемент results должен быть объектом")
            md = item.get("metadata")
            if md is None:
                md = {}
            elif not isinstance(md, dict):
                raise ServiceClientError("rag search: metadata должен быть объектом")
            out.append(
                {
                    "content": item["content"],
                    "score": item["score"],
                    "document_id": item["document_id"],
                    "metadata": md,
                }
            )
        return out

    async def add_document(
        self,
        document_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        *,
        index_profile_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Загрузить текст документа в namespace.
        """
        repo = self._container.rag_repository
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
