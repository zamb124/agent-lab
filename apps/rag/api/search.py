"""
API для семантического поиска.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apps.rag.config import get_rag_settings
from core.billing.exceptions import BillingBalanceBlockedError
from core.logging import get_logger
from core.rag.base_provider import validate_metadata_filters
from core.rag.factory import get_rag_provider
from core.rag.models import RAGGlobalSearchRequest, RAGNamespaceSearchRequest, RAGSearchResult
from core.rag.post_retrieval_rerank import (
    RerankerClientError,
    apply_rerank_after_retrieve,
    apply_rerank_after_retrieve_grouped,
)

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

        results = await rag_provider.search(
            namespace_id=namespace_id,
            query=request.query,
            limit=request.limit,
            filters=request.filters,
            search_options=request,
        )

        results = await apply_rerank_after_retrieve(
            results=results,
            query=request.query,
            provider_name=provider_name,
            request_rerank=request.rerank,
            profile_sd=None,
            settings=settings,
        )

        logger.info(f"Поиск '{request.query}' в {namespace_id}: найдено {len(results)} результатов")

        return SearchResponse(
            results=results,
            query=request.query,
            namespace_id=namespace_id,
            provider=provider_name
        )
    except BillingBalanceBlockedError:
        raise
    except RerankerClientError as e:
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

        results = await rag_provider.search_multiple_namespaces(
            namespace_ids=valid_namespace_ids,
            query=request.query,
            limit=request.limit,
            filters=request.filters,
            search_options=request,
        )

        results = await apply_rerank_after_retrieve_grouped(
            results_by_namespace=results,
            namespace_order=valid_namespace_ids,
            query=request.query,
            provider_name=provider_name,
            request_rerank=request.rerank,
            profile_sd=None,
            settings=settings,
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
    except RerankerClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка глобального поиска: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}")
