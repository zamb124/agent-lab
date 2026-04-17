"""
API для семантического поиска.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.logging import get_logger
from core.rag.base_provider import validate_metadata_filters
from core.rag.models import RAGSearchResult
from core.context import get_context
from core.rag.factory import get_rag_provider
from core.billing.exceptions import BillingBalanceBlockedError
from apps.rag.config import get_rag_settings
from ..dependencies import ContainerDep
from .namespace_access import require_registered_rag_namespace

logger = get_logger(__name__)

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    """Запрос на поиск (опции совпадают с телом RAGRepository.search_namespace)."""

    query: str
    limit: int = 5
    filters: Optional[Dict[str, Any]] = None
    channels: Optional[Dict[str, Any]] = None
    rrf_k: Optional[int] = None
    per_channel_top_k: Optional[int] = None
    rerank: Optional[bool] = None


class SearchResponse(BaseModel):
    """Ответ с результатами поиска"""
    results: List[RAGSearchResult]
    query: str
    namespace_id: str
    provider: str


@router.post("/namespaces/{namespace_id}/search", response_model=SearchResponse)
async def search_in_namespace(
    namespace_id: str,
    request: SearchRequest,
    container: ContainerDep,
    provider: Optional[str] = Query(None, description="RAG provider"),
) -> SearchResponse:
    """
    Выполняет семантический поиск в namespace.
    
    Args:
        namespace_id: ID namespace
        request: Параметры поиска
        provider: Имя провайдера (опционально)
    
    Returns:
        Результаты поиска
    """
    await require_registered_rag_namespace(namespace_id, container)

    settings = get_rag_settings()
    
    try:
        if request.filters is not None:
            validate_metadata_filters(request.filters)
        rag_provider = get_rag_provider(provider, settings=settings) if provider else get_rag_provider(settings=settings)
        provider_name = provider or settings.rag.default_provider
        
        search_kwargs: Dict[str, Any] = {}
        if request.channels is not None:
            search_kwargs["channels"] = request.channels
        if request.rrf_k is not None:
            search_kwargs["rrf_k"] = request.rrf_k
        if request.per_channel_top_k is not None:
            search_kwargs["per_channel_top_k"] = request.per_channel_top_k
        if request.rerank is not None:
            search_kwargs["rerank"] = request.rerank

        results = await rag_provider.search(
            namespace_id=namespace_id,
            query=request.query,
            limit=request.limit,
            filters=request.filters,
            **search_kwargs,
        )
        
        logger.info(f"Поиск '{request.query}' в namespace {namespace_id}: найдено {len(results)} результатов")

        return SearchResponse(
            results=results,
            query=request.query,
            namespace_id=namespace_id,
            provider=provider_name
        )
    except BillingBalanceBlockedError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}")


class GlobalSearchRequest(BaseModel):
    """Запрос на глобальный поиск"""
    query: str
    namespace_ids: List[str]
    limit: int = 5


class GlobalSearchResponse(BaseModel):
    """Ответ с результатами глобального поиска"""
    results: Dict[str, List[RAGSearchResult]]
    query: str
    provider: str


@router.post("/search", response_model=GlobalSearchResponse)
async def global_search(
    request: GlobalSearchRequest,
    container: ContainerDep,
    provider: Optional[str] = Query(None, description="RAG provider"),
) -> GlobalSearchResponse:
    """
    Выполняет поиск по нескольким namespace текущей компании.
    
    Args:
        request: Параметры поиска
        provider: Имя провайдера (опционально)
    
    Returns:
        Результаты поиска по каждому namespace
    """
    # Провайдер сам добавит company_id через контекст, просто передаем namespace names
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
        
        results = await rag_provider.search_multiple_namespaces(
            namespace_ids=valid_namespace_ids,
            query=request.query,
            limit=request.limit
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка глобального поиска: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}")


