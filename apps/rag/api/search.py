"""Поиск RAG: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.rag.di import Di
from apps.rag.models import GlobalSearchResponse, SearchResponse
from apps.rag.realtime.operations import (
    RagGlobalSearchPayload,
    RagNamespaceSearchPayload,
    op_search_defaults,
    op_search_global,
    op_search_namespace,
)
from core.context import require_context
from core.rag.models import RAGGlobalSearchRequest, RAGNamespaceSearchRequest, RAGSearchOptions
from core.types import parse_json_object
from core.websocket import EmptyPayload

router = APIRouter(tags=["search"])


@router.get("/search-defaults", response_model=RAGSearchOptions)
async def get_search_defaults(di: Di) -> RAGSearchOptions:
    return await op_search_defaults(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.post("/namespaces/{namespace_id}/search", response_model=SearchResponse)
async def search_in_namespace(
    namespace_id: str,
    request: RAGNamespaceSearchRequest,
    di: Di,
    provider: Annotated[str | None, Query()] = None,
) -> SearchResponse:
    body = parse_json_object(request.model_dump_json(), "RAGNamespaceSearchRequest")
    body["namespace_id"] = namespace_id
    body["provider"] = provider
    return await op_search_namespace(
        RagNamespaceSearchPayload.model_validate(body),
        user=require_context().user,
        di=di,
    )


@router.post("/search", response_model=GlobalSearchResponse)
async def global_search(
    request: RAGGlobalSearchRequest,
    di: Di,
    provider: Annotated[str | None, Query()] = None,
) -> GlobalSearchResponse:
    body = parse_json_object(request.model_dump_json(), "RAGGlobalSearchRequest")
    body["provider"] = provider
    return await op_search_global(
        RagGlobalSearchPayload.model_validate(body),
        user=require_context().user,
        di=di,
    )
