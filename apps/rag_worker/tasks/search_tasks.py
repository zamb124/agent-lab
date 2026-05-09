"""
Tasks для семантического поиска через pgvector.
"""

from typing import Any, Dict, List, Optional

from apps.rag.container import get_rag_container
from apps.rag_worker.broker import broker
from apps.rag_worker.config import get_settings as get_rag_worker_settings
from core.context import Context, clear_context, set_context
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.rag.post_retrieval_rerank import apply_rerank_after_retrieve

logger = get_logger(__name__)


def _search_context(
    company_id: str | None,
    user_id: str | None,
    namespace_id: str,
) -> Context | None:
    cid = str(company_id).strip() if company_id else ""
    uid = str(user_id).strip() if user_id else ""
    if not cid or not uid:
        return None
    ns = str(namespace_id).strip() or "default"
    return Context(
        user=User(user_id=uid, name="RAG worker search"),
        active_company=Company(company_id=cid, name=cid),
        channel="rag_worker",
        active_namespace=ns,
    )


@broker.task(queue_name="rag")
async def search_task(
    namespace_id: str,
    query: str,
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    company_id: str | None = None,
    user_id: str | None = None,
    channels: Optional[Dict[str, Any]] = None,
    rrf_k: Optional[int] = None,
    per_channel_top_k: Optional[int] = None,
    rerank: Optional[bool] = None,
    retrieval: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    Семантический поиск в vector_documents.

    company_id и user_id опциональны; если оба заданы, выставляется контекст для биллинга реранка.
    """
    logger.info(f"RAG Worker: поиск в namespace {namespace_id}, query='{query[:50]}'")

    ctx = _search_context(company_id, user_id, namespace_id)
    if ctx is not None:
        set_context(ctx)
    try:
        provider = get_rag_container().rag_provider
        search_kw: Dict[str, Any] = {}
        if channels is not None:
            search_kw["channels"] = channels
        if rrf_k is not None:
            search_kw["rrf_k"] = rrf_k
        if per_channel_top_k is not None:
            search_kw["per_channel_top_k"] = per_channel_top_k
        if rerank is not None:
            search_kw["rerank"] = rerank
        if retrieval is not None:
            search_kw["retrieval"] = retrieval
        results = await provider.search(
            namespace_id,
            query,
            limit,
            filters,
            **search_kw,
        )

        settings = get_rag_worker_settings()
        provider_name = settings.rag.default_provider
        results = await apply_rerank_after_retrieve(
            results=results,
            query=query,
            provider_name=provider_name,
            request_rerank=rerank,
            profile_sd=None,
            settings=settings,
        )

        logger.info(f"RAG Worker: найдено {len(results)} результатов")

        return [
            {
                "content": r.content,
                "score": r.score,
                "document_id": r.document_id,
                "document_name": r.document_name,
                "metadata": r.metadata,
            }
            for r in results
        ]
    finally:
        if ctx is not None:
            clear_context()
