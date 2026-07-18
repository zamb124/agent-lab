"""
API для семантического поиска.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import core.tracing.attributes as trace_attributes
from apps.rag.config import get_rag_settings
from core.ai.rerank_client import AIRerankerClientError
from core.billing.exceptions import BillingBalanceBlockedError
from core.logging import get_logger
from core.rag.base_provider import validate_metadata_filters
from core.rag.factory import get_rag_provider
from core.rag.models import (
    RAGGlobalSearchRequest,
    RAGNamespaceSearchRequest,
    RAGSearchOptions,
    RAGSearchResult,
)
from core.rag.post_retrieval_rerank import (
    apply_rerank_after_retrieve,
    apply_rerank_after_retrieve_grouped,
)
from core.rag.rag_http_namespace_search import filter_search_request_options
from core.rag.search_options_resolver import resolve_platform_search_options
from core.tracing.operation_span import traced_operation

from ..dependencies import ContainerDep
from .namespace_access import require_registered_rag_namespace

logger = get_logger(__name__)

router = APIRouter(tags=["search"])


class SearchResponse(BaseModel):
    """Ответ с результатами поиска"""
    results: list[RAGSearchResult]
    query: str
    namespace_id: str
    provider: str


@router.get("/search-defaults", response_model=RAGSearchOptions)
async def get_search_defaults(container: ContainerDep) -> RAGSearchOptions:
    """Platform retrieval defaults из ``rag.document_indexing.search_defaults``."""
    _ = container
    return resolve_platform_search_options(settings=get_rag_settings())


@router.post("/namespaces/{namespace_id}/search", response_model=SearchResponse)
async def search_in_namespace(
    namespace_id: str,
    request: RAGNamespaceSearchRequest,
    container: ContainerDep,
    provider: Annotated[str | None, Query(description="RAG provider")] = None,
) -> SearchResponse:
    """
    Выполняет семантический поиск в namespace.

    Аргументы:
        namespace_id: ID namespace
        request: Параметры поиска
        provider: Имя провайдера (опционально)

    Возвращает:
        Результаты поиска
    """
    await require_registered_rag_namespace(namespace_id, container)

    settings = get_rag_settings()

    try:
        if request.filters is not None:
            validate_metadata_filters(request.filters)
        rag_provider = get_rag_provider(provider, settings=settings) if provider else get_rag_provider(settings=settings)
        provider_name = provider or settings.rag.default_provider

        resolved_search_options = resolve_platform_search_options(
            settings=settings,
            overrides=filter_search_request_options(request),
            per_channel_top_k=request.per_channel_top_k,
        )

        async with traced_operation(
            "rag.search.namespace",
            event_type="rag.search",
            operation_category="rag_search",
            resource_type="rag.namespace",
            resource_id=namespace_id,
            extra_attributes={
                trace_attributes.ATTR_RAG_STAGE: "search",
                "platform.rag.search_pool_size": request.limit,
            },
        ) as span:
            results = await rag_provider.search(
                namespace_id=namespace_id,
                query=request.query,
                limit=request.limit,
                filters=request.filters,
                search_options=resolved_search_options,
            )

            results = await apply_rerank_after_retrieve(
                results=results,
                query=request.query,
                provider_name=provider_name,
                request_rerank=resolved_search_options.rerank,
                profile_sd=None,
                settings=settings,
                request_rerank_max_candidates=resolved_search_options.rerank_max_candidates,
                score_cache=container.rerank_score_cache,
            )
            span.set_attribute("platform.rag.result_count", len(results))

        logger.info(f"Поиск '{request.query}' в {namespace_id}: найдено {len(results)} результатов")

        return SearchResponse(
            results=results,
            query=request.query,
            namespace_id=namespace_id,
            provider=provider_name
        )
    except BillingBalanceBlockedError:
        raise
    except AIRerankerClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}")


class GlobalSearchResponse(BaseModel):
    """Ответ с результатами глобального поиска"""
    results: dict[str, list[RAGSearchResult]]
    query: str
    provider: str


@router.post("/search", response_model=GlobalSearchResponse)
async def global_search(
    request: RAGGlobalSearchRequest,
    container: ContainerDep,
    provider: Annotated[str | None, Query(description="RAG provider")] = None,
) -> GlobalSearchResponse:
    """
    Выполняет поиск по нескольким namespace текущей компании.

    Аргументы:
        request: Параметры поиска
        provider: Имя провайдера (опционально)

    Возвращает:
        Результаты поиска по каждому namespace
    """
    # Провайдер сам добавит company_id через контекст, просто передаём имена namespace
    valid_namespace_ids = request.namespace_ids

    if not valid_namespace_ids:
        raise HTTPException(
            status_code=400,
            detail="No namespaces provided"
        )

    for ns_id in valid_namespace_ids:
        await require_registered_rag_namespace(ns_id, container)

    settings = get_rag_settings()

    try:
        rag_provider = get_rag_provider(provider, settings=settings) if provider else get_rag_provider(settings=settings)
        provider_name = provider or settings.rag.default_provider

        if request.filters is not None:
            validate_metadata_filters(request.filters)

        resolved_search_options = resolve_platform_search_options(
            settings=settings,
            overrides=filter_search_request_options(request),
            per_channel_top_k=request.per_channel_top_k,
        )

        results = await rag_provider.search_multiple_namespaces(
            namespace_ids=valid_namespace_ids,
            query=request.query,
            limit=request.limit,
            filters=request.filters,
            search_options=resolved_search_options,
        )

        results = await apply_rerank_after_retrieve_grouped(
            results_by_namespace=results,
            namespace_order=valid_namespace_ids,
            query=request.query,
            provider_name=provider_name,
            request_rerank=resolved_search_options.rerank,
            profile_sd=None,
            settings=settings,
            request_rerank_max_candidates=resolved_search_options.rerank_max_candidates,
            score_cache=container.rerank_score_cache,
        )

        total_results = sum(len(r) for r in results.values())
        logger.info(f"Глобальный поиск '{request.query}': найдено {total_results} результатов")

        return GlobalSearchResponse(
            results=results,
            query=request.query,
            provider=provider_name
        )
    except BillingBalanceBlockedError:
        raise
    except AIRerankerClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка глобального поиска: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}")
