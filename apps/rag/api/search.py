"""
API для семантического поиска.
"""

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from core.config import get_settings
from core.logging import get_logger
from core.rag.factory import get_rag_provider
from core.rag_indexing_schema import IndexProfileConfig, IndexProfileSearchDefaults
from core.rag.models import RAGSearchResult
from ..services.reranker_client import RerankerClientError

from ..container import RAGContainer
from ..services.rerank_after_retrieve import (
    apply_rerank_after_retrieve,
    apply_rerank_after_retrieve_grouped,
)
from ..dependencies import get_container_dep

logger = get_logger(__name__)

router = APIRouter(tags=["search"])


class SearchChannelsRequest(BaseModel):
    """Каналы поиска (семантика / лексика). Режим (только семантика, только лексика, RRF при обоих) выводится из флагов."""

    semantic: bool = True
    lexical: bool = False

    @model_validator(mode="after")
    def at_least_one_channel(self) -> "SearchChannelsRequest":
        if not self.semantic and not self.lexical:
            raise ValueError("Нужен хотя бы один канал: semantic или lexical")
        return self


class SearchRequest(BaseModel):
    """Запрос на поиск"""

    query: str
    limit: int = 5
    filters: Optional[Dict[str, Any]] = None
    channels: Optional[SearchChannelsRequest] = None
    rrf_k: Optional[int] = Field(default=None, gt=0)
    per_channel_top_k: Optional[int] = Field(default=None, gt=0)
    rerank: Optional[bool] = None


class SearchResponse(BaseModel):
    """Ответ с результатами поиска"""

    results: List[RAGSearchResult]
    query: str
    namespace_id: str
    provider: str


def _search_kwargs_channels_only(request: SearchRequest) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if request.channels is not None:
        out["channels"] = request.channels.model_dump()
    if request.rrf_k is not None:
        out["rrf_k"] = request.rrf_k
    if request.per_channel_top_k is not None:
        out["per_channel_top_k"] = request.per_channel_top_k
    return out


def _apply_search_defaults_to_kwargs(
    base: Dict[str, Any],
    cfg: IndexProfileConfig,
) -> Optional[IndexProfileSearchDefaults]:
    sd = cfg.search_defaults
    if sd is None:
        return None
    if base.get("channels") is None and sd.channels is not None:
        base["channels"] = sd.channels.model_dump()
    if base.get("rrf_k") is None and sd.rrf_k is not None:
        base["rrf_k"] = sd.rrf_k
    if base.get("per_channel_top_k") is None and sd.per_channel_top_k is not None:
        base["per_channel_top_k"] = sd.per_channel_top_k
    return sd


def _merge_search_kwargs_from_settings(
    request: SearchRequest,
    document_indexing: IndexProfileConfig,
) -> Tuple[Dict[str, Any], Optional[IndexProfileSearchDefaults]]:
    base = _search_kwargs_channels_only(request)
    sd = _apply_search_defaults_to_kwargs(base, document_indexing)
    return base, sd


@router.post("/namespaces/{namespace_id}/search", response_model=SearchResponse)
async def search_in_namespace(
    namespace_id: str,
    request: SearchRequest,
    provider: Optional[str] = Query(None, description="RAG provider"),
    container: RAGContainer = Depends(get_container_dep),
) -> SearchResponse:
    """
    Выполняет семантический поиск в namespace.

    Дефолты каналов / RRF подмешиваются из ``rag.document_indexing.search_defaults``;
    тело запроса перекрывает их.

    После retrieve при включённом ``rerank`` вызывается HTTP-сервис реранкера;
    ошибки сервиса не маскируются.
    """
    settings = get_settings()

    try:
        rag_provider = get_rag_provider(provider) if provider else container.rag_provider
        provider_name = provider or settings.rag.default_provider

        extra, profile_sd = _merge_search_kwargs_from_settings(
            request, settings.rag.document_indexing
        )

        results = await rag_provider.search(
            namespace_id=namespace_id,
            query=request.query,
            limit=request.limit,
            filters=request.filters,
            **extra,
        )

        results = await apply_rerank_after_retrieve(
            results=results,
            query=request.query,
            provider_name=provider_name,
            request_rerank=request.rerank,
            profile_sd=profile_sd,
            settings=settings,
        )

        logger.info(
            f"Поиск '{request.query}' в namespace {namespace_id}: найдено {len(results)} результатов"
        )

        return SearchResponse(
            results=results,
            query=request.query,
            namespace_id=namespace_id,
            provider=provider_name,
        )
    except RerankerClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}") from e


class GlobalSearchRequest(BaseModel):
    """Запрос на глобальный поиск"""

    query: str
    namespace_ids: List[str]
    limit: int = 5
    filters: Optional[Dict[str, Any]] = None
    channels: Optional[SearchChannelsRequest] = None
    rrf_k: Optional[int] = Field(default=None, gt=0)
    per_channel_top_k: Optional[int] = Field(default=None, gt=0)
    rerank: Optional[bool] = None


class GlobalSearchResponse(BaseModel):
    """Ответ с результатами глобального поиска"""

    results: Dict[str, List[RAGSearchResult]]
    query: str
    provider: str


def _global_search_kwargs_channels_only(request: GlobalSearchRequest) -> Dict[str, Any]:
    base: Dict[str, Any] = {}
    if request.channels is not None:
        base["channels"] = request.channels.model_dump()
    if request.rrf_k is not None:
        base["rrf_k"] = request.rrf_k
    if request.per_channel_top_k is not None:
        base["per_channel_top_k"] = request.per_channel_top_k
    return base


def _merge_global_search_kwargs(
    request: GlobalSearchRequest,
    document_indexing: IndexProfileConfig,
) -> Tuple[Dict[str, Any], Optional[IndexProfileSearchDefaults]]:
    base = _global_search_kwargs_channels_only(request)
    sd = _apply_search_defaults_to_kwargs(base, document_indexing)
    return base, sd


# TODO(RAG-92): переписать сквозную логику multi-namespace (см. RAG_TASKS.md).
@router.post("/search", response_model=GlobalSearchResponse)
async def global_search(
    request: GlobalSearchRequest,
    provider: Optional[str] = Query(None, description="RAG provider"),
    container: RAGContainer = Depends(get_container_dep),
) -> GlobalSearchResponse:
    """
    Выполняет поиск сразу по нескольким namespace текущей компании.

    При включённом лексическом канале (или обоих каналах для RRF) поиск выполняется по каждому
    namespace отдельно. Только семантика без лексики — один общий SQL по выбранным namespace (pgvector).
    """
    valid_namespace_ids = request.namespace_ids

    if not valid_namespace_ids:
        raise HTTPException(
            status_code=400,
            detail="No namespaces provided",
        )

    settings = get_settings()

    try:
        rag_provider = get_rag_provider(provider) if provider else container.rag_provider
        provider_name = provider or settings.rag.default_provider

        extra, profile_sd = _merge_global_search_kwargs(
            request, settings.rag.document_indexing
        )

        results = await rag_provider.search_multiple_namespaces(
            namespace_ids=valid_namespace_ids,
            query=request.query,
            limit=request.limit,
            filters=request.filters,
            **extra,
        )

        reranked = await apply_rerank_after_retrieve_grouped(
            results_by_namespace=results,
            namespace_order=valid_namespace_ids,
            query=request.query,
            provider_name=provider_name,
            request_rerank=request.rerank,
            profile_sd=profile_sd,
            settings=settings,
        )

        total_results = sum(len(r) for r in reranked.values())
        logger.info(f"Глобальный поиск '{request.query}': найдено {total_results} результатов")

        return GlobalSearchResponse(
            results=reranked,
            query=request.query,
            provider=provider_name,
        )
    except RerankerClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Ошибка глобального поиска: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}") from e
